from sageopt.coniclifts.constraints.constraint import Constraint
from sageopt.coniclifts.cones import Cone
import numpy as np


class ElementwiseConstraint(Constraint):

    _CURVATURE_CHECK_ = False

    _ELEMENTWISE_CONSTRAINT_ID_ = 0

    _ELEMENTWISE_OPS_ = ('==', '<=', '>=')

    def __init__(self, lhs, rhs, operator):
        self.id = ElementwiseConstraint._ELEMENTWISE_CONSTRAINT_ID_
        ElementwiseConstraint._ELEMENTWISE_CONSTRAINT_ID_ += 1
        self.lhs = lhs
        self.rhs = rhs
        self.initial_operator = operator
        name_str = 'Elementwise[' + str(self.id) + '] : '
        self.name = name_str
        if operator == '==':
            self.expr = (self.lhs - self.rhs).as_expr().ravel()
            if ElementwiseConstraint._CURVATURE_CHECK_ and not self.expr.is_affine():
                raise RuntimeError('Equality constraints must be affine.')
            self.operator = '=='  # now we are a linear constraint "self.expr == 0"
            self.epigraph_checked = True
        else:  # elementwise inequality.
            if operator == '>=':
                self.expr = (self.rhs - self.lhs).as_expr().ravel()
            else:
                self.expr = (self.lhs - self.rhs).as_expr().ravel()
            if ElementwiseConstraint._CURVATURE_CHECK_ and not all(self.expr.is_convex()):
                raise RuntimeError('Cannot canonicalize.')
            self.operator = '<='  # now we are a convex constraint "self.expr <= 0"
            self.epigraph_checked = False

    def variables(self):
        return self.expr.variables()

    def is_affine(self):
        if self.operator in ['==']:
            return True
        else:
            return self.expr.is_affine()

    def is_elementwise(self):
        return True

    def is_setmem(self):
        return False

    def conic_form(self):
        from sageopt.coniclifts.base import ScalarVariable
        # This function assumes that every Constraint "c" in "constraints" has
        # c.is_affine() == True. (For constraints that were not affine when first
        # constructed, we must have since performed an epigraph substitution to
        # handle the nonlinear terms.)
        #
        # The vector "K" returned by this function may only include entries for
        # the zero cone and R_+.
        #
        # Note: signs on coefficients are inverted in this function. This happens
        # because flipping signs on A and b won't affect the zero cone, and
        # it correctly converts affine constraints of the form "expression <= 0"
        # to the form "-expression >= 0". We want this latter form because our
        # primitive cones are the zero cone and R_+.
        if not self.epigraph_checked:
            raise RuntimeError('Cannot canonicalize without check for epigraph substitution.')
        m = self.expr.size
        b = np.empty(shape=(m,))
        if self.operator == '==':
            K = [Cone('0', m)]
        elif self.operator == '<=':
            K = [Cone('+', m)]
        else:
            raise RuntimeError('Unknown operator.')
        A_rows, A_cols, A_vals = [], [], []
        for i, se in enumerate(self.expr.flat):
            if len(se.atoms_to_coeffs) == 0:
                b[i] = -se.offset
                A_rows.append(i)
                A_cols.append(int(ScalarVariable.curr_variable_count())-1)
                A_vals.append(0)  # make sure scipy infers correct dimensions later on.
            else:
                b[i] = -se.offset
                A_rows += [i] * len(se.atoms_to_coeffs)
                col_idx_to_coeff = [(a.id, c) for a, c in se.atoms_to_coeffs.items()]
                A_cols += [atom_id for (atom_id, _) in col_idx_to_coeff]
                A_vals += [-c for (_, c) in col_idx_to_coeff]
        return A_vals, np.array(A_rows), A_cols, b, K, []

    def violation(self, norm=None):
        if norm is None:
            def norm(x):
                if x.size == 1:
                    return np.abs(float(x))
                else:
                    return np.linalg.norm(x, ord=2)
        expr = (self.lhs - self.rhs).as_expr()
        expr_val = expr.value()
        if self.initial_operator == '<=':
            residual = np.max(0, expr_val)
        elif self.initial_operator == '>=':
            residual = np.min(0, expr_val)
        else:
            residual = np.abs(expr_val)
        residual = residual.ravel()
        viol = norm(residual)
        return viol
