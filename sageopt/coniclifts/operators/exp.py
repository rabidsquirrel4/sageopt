import numpy as np

from sageopt.coniclifts.base import NonlinearScalarAtom, Expression, ScalarExpression, Variable, ScalarVariable
from sageopt.coniclifts.cones import Cone


def weighted_sum_exp(c, x):
    """
    Return a coniclifts ScalarExpression representing the signomial

        sum([ci * e^xi for (ci, xi) in (c, x)])

    :param c: a numpy ndarray of nonnegative numbers.
    :param x: a coniclifts Expression of the same size as c.
    """
    if not isinstance(x, Expression):
        x = Expression(x)
    if not isinstance(c, np.ndarray):
        c = np.array(c)
    if np.any(c < 0):
        raise RuntimeError('Epigraphs of non-constant signomials with negative terms are not supported.')
    if x.size != c.size:
        raise RuntimeError('Incompatible arguments.')
    x = x.ravel()
    c = c.ravel()
    kvs = []
    for i in range(x.size):
        if c[i] != 0:
            kvs.append((Exponential(x[i]), c[i]))
    d = dict(kvs)
    se = ScalarExpression(d, 0, verify=False)
    expr = se.as_expr()
    return expr


class Exponential(NonlinearScalarAtom):

    _EXPONENTIAL_COUNTER_ = 0

    @staticmethod
    def __atom_text__():
        return 'Exponential'

    def __init__(self, x):
        """
        Used to represent the epigraph of "e^x"
        :param x:
        """
        self._id = Exponential._EXPONENTIAL_COUNTER_
        Exponential._EXPONENTIAL_COUNTER_ += 1
        self._args = (self.parse_arg(x),)
        self.aux_var = None
        pass

    def is_convex(self):
        return True

    def is_concave(self):
        return False

    def epigraph_conic_form(self):
        """
        Refer to coniclifts/standards/cone_standards.txt to see that
        "(x, y) : e^x <= y" is represented as "(x, y, 1) \in K_{exp}".
        :return:
        """
        if self.aux_var is None:
            v = Variable(shape=(), name='_exp_epi_[' + str(self.id) + ']_')
            self.aux_var = v[()].scalar_variables()[0]
        b = np.zeros(3,)
        K = [Cone('e', 3)]
        A_rows, A_cols, A_vals = [], [], []
        x = self.args[0]
        # first coordinate
        A_rows += (len(x) - 1) * [0]
        A_cols = [var.id for var, co in x[:-1]]
        A_vals = [co for var, co in x[:-1]]
        b[0] = x[-1][1]
        # second coordinate
        A_rows.append(1),
        A_cols.append(self.aux_var.id)
        A_vals.append(1)
        # third coordinate (zeros for A, but included to infer correct dims later on)
        A_rows.append(2)
        A_cols.append(ScalarVariable.curr_variable_count() - 1)
        A_vals.append(0)
        b[2] = 1
        return A_vals, np.array(A_rows), A_cols, b, K, self.aux_var

    def value(self):
        x_list = self.args[0]
        d = dict(x_list[:-1])
        x_se = ScalarExpression(d, x_list[-1][1], verify=False)
        x_val = x_se.value()
        val = np.exp(x_val)
        return val
