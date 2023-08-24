# MIT License
#
# Copyright (c) 2022 Quandela
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# As a special exception, the copyright holders of exqalibur library give you
# permission to combine exqalibur with code included in the standard release of
# Perceval under the MIT license (or modified versions of such code). You may
# copy and distribute such a combined system following the terms of the MIT
# license for both exqalibur and Perceval. This exception for the usage of
# exqalibur is limited to the python bindings used by Perceval.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.


import copy
import numpy as np
from math import factorial
from scipy.special import comb
from collections import defaultdict

from ._abstract_backends import AProbAmpliBackend
from perceval.utils import BasicState
from perceval.components import ACircuit


class MPSBackend(AProbAmpliBackend):
    """
    The state of the system is written in form of an MPS and
    updated step-by-step by a circuit propagation algorithm.

    Approximate the probability amplitudes with a cutoff -> bond Dimension in an MPS.
    - For now only supports Phase shifters and Beam Splitters
    """

    def __init__(self):
        super().__init__()
        self._s_min = 1e-8  # minimum accepted value for singular values
        self._cutoff = None  # Bond dimension of MPS
        self._compiled_input = None
        self._current_input = None
        self._res = defaultdict(lambda: defaultdict(lambda: np.array([0])))
        # _res stores output of the state compilation in MPS.
        # It is a Nested DefaultDict. The outermost dict has "input_states"
        # as keys with values=DefaultDict. We can do multiple computation
        # for different input_states.
        # The 2nd (nested inside) DefaultDict has 2 keys "gamma" and "sv". They
        # represent the matrices $\Gamma$ and $\lambda$ of the MPS for a
        # given input_state. Their values are numpy arrays containing the full MPS.

    @property
    def name(self) -> str:
        return "MPS"

    def set_cutoff(self, cutoff_val: int):
        """
        Cut-off defines the Bond dimension (Schmidt rank of the decomposition of the
        state) of an MPS; in other words, how well approximated the state is.
        """
        assert isinstance(cutoff_val, int), "cutoff must be an integer"
        self._cutoff = cutoff_val

    def set_circuit(self, circuit: ACircuit):
        super().set_circuit(circuit)
        C = self._circuit
        for r, c in C:
            assert c.compute_unitary(use_symbolic=False).shape[0] <= 2, \
                "MPS backend can not be used with components of using more than 2 modes"
        if self._cutoff is None:
            self._cutoff = C.m  # sets the value of cut-off at circuit creation if no _cutoff = Num of modes of circuit

    def set_input_state(self, input_state: BasicState):
        super().set_input_state(input_state)
        self._compile()

    def prob_amplitude(self, output_state: BasicState) -> complex:
        """
        This takes in the expected output states, reads the input and from
        self._res extracts the corresponding gamma and diagonal sv matrices.
        All of this goes to mps_in_list -> each element in order is gamma-sv-gamma-sv-...
        Returns the full contraction -> multidot of all -> which I expect to be the tensor
        containing the prob amplitude coefficients |psi> = c_tensor |pure statevectors>
        """
        m = self._input_state.m
        mps_in_list = []
        self._current_input = tuple(self._input_state)
        for k in range(m - 1):
            mps_in_list.append(self._res[tuple(self._input_state)]["gamma"][k, :, :, output_state[k]])
            # _res[1ST LEVEL: selects dict -> given input state][2ND LEVEL: selects "gamma" matrix key of that]
            # [3RD LEVEL: gamma is np.array -> first chooses kth mode gamma and then selects the segment
            # corresponding to the number of photon in that mode of the output_state being considered.
            mps_in_list.append(self._sv_diag(k))
            # alternately takes in each gamma and singular value matrices (diagonal) -> puts them in a list
        mps_in_list.append(self._res[tuple(self._input_state)]["gamma"][m - 1, :, :, output_state[m - 1]])
        # Inserting the last gamma into MPS outside the loop as there is no sv after that.

        # multi_dot is optimised by numpy to find the best way to take products of 2 or more arrays in a single command
        # todo: find out why is the desired result is always at [0,0]
        return np.linalg.multi_dot(mps_in_list)[0, 0]

    def _compile(self) -> bool:
        C = self._circuit
        var = [float(p) for p in C.get_parameters()]
        if self._compiled_input and self._compiled_input[0] == var and self._input_state in self._res:
            # checks if a given input state for a circuit is already computed
            return False
        self._compiled_input = copy.copy((var, self._input_state))
        self._current_input = None  # todo: ERIC - do I need to set it to None again?

        # TODO : ERIC I am not sure what to do here I had the following comment here
        #  allow any StateVector as in stepper, or a list as in SLOS?
        # self._input_state *= BasicState([0] * (self._input_state.m - self._input_state.m))

        self._n = self._input_state.n  # total number of photons
        self._d = self._n + 1  # possible num of photons in each mode {0,1,2,...,n}
        self._cutoff = min(self._cutoff, self._d ** (self._input_state.m//2))
        # choosing a cut-off smaller than the limit as the size of matrix increases
        # exponentially with cutoff
        # this is the Schmidt's rank or bond dimension ($\chi$ in Thibaud's notes)

        self._gamma = np.zeros((self._input_state.m, self._cutoff, self._cutoff, self._d), dtype='complex_')
        # Gamma matrices of the MPS - array shape (m, $\chi$, $\chi$, d)
        # Each Gamma matrix of MPS, in theory, have 3 indices.
        # The first index 'm' here is used to represent modes - all gammas of MPS stored in a single array
        for i in range(self._input_state.m):
            self._gamma[i, 0, 0, self._input_state[i]] = 1

        self._sv = np.zeros((self._input_state.m, self._cutoff))
        # sv matrices store singular values - array shape (m, $\chi$)
        # sv are vectors of length $\chi$. Similar to gamma, the first index 'm' indexes mode.
        self._sv[:, 0] = 1  # first column set to 1

        # This initialization of MPS (gamma and sv) fixes the input state to be completely separable
        # and a pure BasicState (no superposition); hence would have only 1 non-zero element whose value = 1.
        # It is simply written based on this choice as the SVD of such a structure would exactly look like this

        # todo: maybe make the initialization of MPS more generic - to include mixed/superposed states as input
        # Suggestions - ITensors(Julia), Qiskit

        for r, c in C:
            # r -> tuple -> lists the modes where the component c is connected
            self._apply(r, c)

        self._res[tuple(self._input_state)]["gamma"] = self._gamma.copy()
        self._res[tuple(self._input_state)]["sv"] = self._sv.copy()

        return True

    def _apply(self, r, c):
        """
        Applies the components of the circuit iteratively to update the MPS.

        :param r: List of the mode positions for a component of the Circuit
        :param c: The component
        """
        u = c.compute_unitary(False)
        k_mode = r[0]  # k-th mode is where the upper mode(only) of the BS(PS) component is connected
        if len(u) == 2:
            # BS
            self.update_state_2_mode(k_mode, u)  # --> quandelibc
        elif len(u) == 1:
            # PS
            self.update_state_1_mode(k_mode, u)  # --> quandelibc

########################################################################################
# Starting here everything must be in quandelibc ## todo:implement

    def update_state_1_mode(self, k, u):
        """
        tensor contraction between the corresponding mode's "$\Gamma$" of the MPS
        and the transition matrix "U" of phase shifter for that mode [_transition_matrix_1_mode].
        """
        self._gamma[k] = np.tensordot(self._gamma[k], self._transition_matrix_1_mode(u), axes=(2, 0))
        # gamma[k] -> takes the kth slice from first dimension -> selects gamma of kth mode
        # gamma[k].shape=($\chi$, $\chi$, d) and _transition_matrix_1_mode(u).shape=(d, d).
        # The contraction is on the free index 'd'.
        # Assigns the result to the same gamma[k] returning the shape ($\chi$, $\chi$, d)

    def _transition_matrix_1_mode(self, u):
        """
        transition matrix "U" related to the application of a phase shifter one a single mode.

        size of this "U" depends on the possible number of photons {0,1,2,...n} ==> d=n+1.
        returns the full transition matrix "U" related to the component that will update the
        corresponding mode's "gamma" of the matrix product state

        :param u: the unitary matrix for single mode component - PS
        :returns big_u: np.ndarray of the corresponding transition matrix
        """
        d = self._d
        big_u = np.zeros((d, d), dtype='complex_')
        for i in range(d):
            big_u[i, i] = u[0, 0] ** i
        return big_u

    def update_state_2_mode(self, k, u):
        """
        takes the gamma->kth and (k+1)th + corresponding $\lambda$-s -> contracts the entire thing
        with 2 mode beam splitter, performs some reshaping and then svd to re-build the corresponding
        segment of MPS.
        """

        if 0 < k < self._input_state.m - 2:  # BS anywhere except the first and the last mode
            # all gamma[k,:].shape=($\chi$, $\chi$, d) and _sv_diag(k).shape=($\chi$, $\chi$)
            theta = np.tensordot(self._sv_diag(k - 1), self._gamma[k, :], axes=(1, 0))  # theta.shape=($\chi$,$\chi$,d)
            theta = np.tensordot(theta, self._sv_diag(k), axes=(1, 0))  # theta.shape=($\chi$, d, $\chi$)
            theta = np.tensordot(theta, self._gamma[k + 1, :], axes=(2, 0))  # theta.shape=($\chi$, d, $\chi$, d)
            theta = np.tensordot(theta, self._sv_diag(k + 1), axes=(2, 0))  # theta.shape=($\chi$, d, d, $\chi$)
            # contraction of the corresponding matrices of MPS finished until here
            theta = np.tensordot(theta, self._transition_matrix_2_mode(u), axes=([1, 2], [0, 1]))
            # input->theta.shape=($\chi$, d, d, $\chi$) and big_u.shape(d,d,d,d)
            # output->theta.shape($\chi$, $\chi$, d, d)

        elif k == 0:
            # BS connected between the first 2 modes -> Edge of circuit
            # all gamma[k,:].shape=($\chi$, $\chi$, d) and _sv_diag(k).shape=($\chi$, $\chi$)
            theta = np.tensordot(self._gamma[k, :], self._sv_diag(k), axes=(1, 0))  # theta.shape=($\chi$, d, $\chi$)
            theta = np.tensordot(theta, self._gamma[k + 1, :], axes=(2, 0))  # theta.shape=($\chi$, d, $\chi$, d)
            theta = np.tensordot(theta, self._sv_diag(k + 1), axes=(2, 0))  # theta.shape=($\chi$, d, d, $\chi$)
            theta = np.tensordot(theta, self._transition_matrix_2_mode(u), axes=([1, 2], [0, 1]))
            # input->theta.shape=($\chi$, d, d, $\chi$) and big_u.shape(d,d,d,d)
            # output->theta.shape($\chi$, $\chi$, d, d)

        elif k == self._input_state.m - 2:
            # BS connected between the last 2 modes -> Edge of circuit
            # all gamma[k,:].shape=($\chi$, $\chi$, d) and _sv_diag(k).shape=($\chi$, $\chi$)
            theta = np.tensordot(self._sv_diag(k - 1), self._gamma[k, :], axes=(1, 0))  # theta.shape=($\chi$,$\chi$,d)
            theta = np.tensordot(theta, self._sv_diag(k), axes=(1, 0))  # theta.shape=($\chi$, d, $\chi$)
            theta = np.tensordot(theta, self._gamma[k + 1, :], axes=(2, 0))  # theta.shape=($\chi$, d, $\chi$, d)
            theta = np.tensordot(theta, self._transition_matrix_2_mode(u), axes=([1, 3], [0, 1]))
            # input->theta.shape = ($\chi$, d, $\chi$, d) and big_u.shape(d, d, d, d)
            # output->theta.shape($\chi$, $\chi$, d, d)

        theta = theta.swapaxes(1, 2).swapaxes(0, 1).swapaxes(2, 3)  # resulting theta.shape(d, $\chi$, d, $\chi$)
        theta = theta.reshape(self._d * self._cutoff, self._d * self._cutoff)  # theta.shape (d x $\chi$, d x $\chi$)
        v, s, w = np.linalg.svd(theta)
        # svd of the tensor after component is applied to extract the MPS form
        # in standard notation SVD is written as M=USV, but we keep 'u' for unitary,
        # Here:: U->v [v.shape=(d, $\chi$, d, $\chi$)],
        # S->s [s.shape=($\chi$)], V->w [w.shape=(d, $\chi$, d, $\chi$)]

        # todo: not sure about indices and their sizes
        v = v.reshape(self._d, self._cutoff, self._d * self._cutoff).swapaxes(0, 1).swapaxes(1, 2)[:, :self._cutoff]
        w = w.reshape(self._d * self._cutoff, self._d, self._cutoff).swapaxes(1, 2)[:self._cutoff]
        s = s[:self._cutoff]  # restricting the size of SV matrices to cut_off -> truncation

        self._sv[k] = np.where(s > self._s_min, s, 0)  # updating corresponding sv after the action of BS
        # todo : _s_min is too low, do we really need this todo: ask Rawad

        # todo: below - seems weird, investigate
        if k > 0:
            rank = np.nonzero(self._sv[k - 1])[0][-1] + 1
            self._gamma[k, :rank] = v[:rank] / self._sv[k - 1, :rank][:, np.newaxis, np.newaxis]
            self._gamma[k, rank:] = 0
        else:
            self._gamma[k] = v
        if k < self._input_state.m - 2:
            rank = np.nonzero(self._sv[k + 1])[0][-1] + 1
            self._gamma[k + 1, :, :rank] = (w[:, :rank] / self._sv[k + 1, :rank][:, np.newaxis])
            self._gamma[k + 1, :, rank:] = 0
        else:
            self._gamma[k + 1] = w

    def _transition_matrix_2_mode(self, u):
        """
        this function computes the elements
        (I,J) = (i_k, i_k+1, j_k, j_k+1) of the matrix U_k,k+1.
        This is concerned with the action of beam splitter between given 2 modes.
        input parameter u is the unitary matrix of the Beam splitter - 2x2 matrix
        The formula for constructing the larger U to contract with the MPS is in
        Thibaud report.
        """
        u11, u12, u21, u22 = u[0, 0], u[0, 1], u[1, 0], u[1, 1]
        d = self._d
        big_u = np.zeros((d, d, d, d), dtype='complex_')  # matrix corresponding to action of BS on the 2 modes
        # todo: find a way to vectorize and remove "for" loops
        for n1 in range(d):  # n1 -> number of photons in mode 1
            for n2 in range(d):  # n2 -> number of photons in mode 2
                n_tot = n1 + n2
                outputs = np.zeros((d, d), dtype='complex_')  # unitary of BS for a fixed n1 and n2 entering the modes
                if n_tot <= self._n:  # cannot exceed the total number of photons in the circuit
                    for k1 in range(n1+1):
                        for k2 in range(n2+1):
                            # of those (n1,n2) entering -> (k1,k2) combinations
                            outputs[k1 + k2, n_tot - (k1 + k2)] += comb(n1, k1) * comb(n2, k2) \
                                                                * (u11**k1 * u12**(n1-k1) * u21**k2 * u22**(n2-k2)) \
                                                                * (np.sqrt(factorial(k1+k2) * factorial(n_tot-k1-k2)))
                big_u[n1, n2, :] = outputs / (np.sqrt(factorial(n1) * factorial(n2)))
        return big_u

    def _sv_diag(self, k):
        """
        Creates the diagonal matrix containing the singular values of
        the matrices in the MPS.
        """
        if self._res[self._current_input]["sv"].any():
            sv = self._res[self._current_input]["sv"]
            # todo: clarify with Eric -
            #  would this not be the same as else ? Also, by the time this is called "sv" is set in _res
        else:
            sv = self._sv
        sv_diag = np.zeros((self._cutoff, self._cutoff))
        np.fill_diagonal(sv_diag, sv[k, :])
        return sv_diag
