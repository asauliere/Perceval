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
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

from perceval.serialization import _schema_circuit_pb2 as pb
from perceval.serialization._parameter_serialization import deserialize_parameter
from perceval.serialization._matrix_serialization import deserialize_pb_matrix
import perceval.components.base_components as comp


def deserialize_ps(serial_ps: pb.PhaseShifter) -> comp.PS:
    return comp.PS(deserialize_parameter(serial_ps.phi))


def deserialize_generic_bs(serial_bs: pb.BeamSplitterComplex) -> comp.GenericBS:
    args = {}
    if serial_bs.HasField('R'):
        args['R'] = deserialize_parameter(serial_bs.R)
    if serial_bs.HasField('theta'):
        args['theta'] = deserialize_parameter(serial_bs.theta)
    args['phi_a'] = deserialize_parameter(serial_bs.phi_a)
    args['phi_b'] = deserialize_parameter(serial_bs.phi_b)
    args['phi_d'] = deserialize_parameter(serial_bs.phi_d)
    return comp.GenericBS(**args)


def deserialize_perm(serial_perm) -> comp.PERM:
    return comp.PERM([x for x in serial_perm.permutations])


def deserialize_unitary(serial_unitary) -> comp.Unitary:
    m = deserialize_pb_matrix(serial_unitary.mat)
    return comp.Unitary(U=m)


def deserialize_simple_bs(serial_bs: pb.BeamSplitter) -> comp.SimpleBS:
    args = {}
    if serial_bs.HasField('R'):
        args['R'] = deserialize_parameter(serial_bs.R)
    if serial_bs.HasField('theta'):
        args['theta'] = deserialize_parameter(serial_bs.theta)
    return comp.SimpleBS(**args)


def deserialize_wp(serial_wp) -> comp.WP:
    return comp.WP(deserialize_parameter(serial_wp.delta), deserialize_parameter(serial_wp.xsi))


def deserialize_qwp(serial_qwp) -> comp.QWP:
    return comp.QWP(deserialize_parameter(serial_qwp.xsi))


def deserialize_hwp(serial_hwp) -> comp.HWP:
    return comp.HWP(deserialize_parameter(serial_hwp.xsi))


def deserialize_dt(serial_dt) -> comp.TD:
    return comp.TD(deserialize_parameter(serial_dt.dt))


def deserialize_pr(serial_pr) -> comp.PR:
    return comp.PR(deserialize_parameter(serial_pr.delta))


def deserialize_pbs(_) -> comp.PBS:
    return comp.PBS()