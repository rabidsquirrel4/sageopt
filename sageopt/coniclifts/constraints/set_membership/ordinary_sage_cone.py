"""
   Copyright 2019 Riley John Murray

   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at

     http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.
"""
from sageopt.coniclifts.constraints.set_membership.setmem import SetMembership
from sageopt.coniclifts.base import Variable, Expression
from sageopt.coniclifts.cones import Cone
from sageopt.coniclifts.operators import affine as aff
from sageopt.coniclifts.operators.norms import vector2norm
from sageopt.coniclifts.operators.precompiled.relent import sum_relent, elementwise_relent
from sageopt.coniclifts.operators.precompiled import affine as compiled_aff
from sageopt.coniclifts.problems.problem import Problem
from sageopt.coniclifts.standards.constants import maximize as CL_MAX, solved as CL_SOLVED, minimize as CL_MIN
import numpy as np
import scipy.special as special_functions
import warnings
from sageopt.coniclifts.constraints.set_membership.conditional_sage_cone import ExpCoverHelper


_ELIMINATE_TRIVIAL_AGE_CONES_ = True

_REDUCTION_SOLVER_ = 'ECOS'


class PrimalOrdinarySageCone(SetMembership):
    """
    Represent the constraint that a certain vector ``c`` belongs to the primal ordinary SAGE cone
    induced by a given set of exponent vectors ``alpha``. Maintain metadata such as summand
    "AGE vectors", and auxiliary variables needed to represent the primal SAGE cone in terms of
    coniclifts primitives. Instances of this class automatically apply a presolve procedure based
    on any constant components in ``c``, and geometric properties of the rows of ``alpha``.

    Parameters
    ----------

    c : Expression

        The vector subject to the primal SAGE-cone constraint.

    alpha : ndarray

        The matrix of exponent vectors defining the primal SAGE cone. ``alpha.shape[0] == c.size.``

    name : str

        Uniquely identifies this Constraint in the model where it appears. Serves as a suffix
        for the name of any auxiliary Variable created when compiling to the coniclifts-standard.

    covers : Dict[int, ndarray]

        ``covers[i]`` is a boolean selector array, indicating which exponents have a nontrivial role
        in representing the i-th AGE cone. A standard value for this argument is automatically
        constructed when unspecified. Providing this value can reduce the overhead associated
        with presolving a SAGE constraint.

    Attributes
    ----------

    alpha : ndarray

         The matrix whose rows define the exponent vectors of this primal SAGE cone.

    c : Expression

        The vector subject to the primal SAGE-cone constraint.

    age_vectors : Dict[int, Expression]

        ``age_vectors[i]`` is a lifted representation of ``c_vars[i]``. If ``c_vars`` and
        ``nu_vars`` are assigned feasible values, then we should have that ``age_vectors[i]``
        belongs to the i-th AGE cone induced by ``alpha``, and that
        ``self.c.value == np.sum([ av.value for av in age_vectors.values() ])``.

    m : int

        The number of rows in ``alpha``; the number of entries in ``c``.

    n : int

        The number of columns in ``alpha``.

    nu_vars : Dict[int, Variable]

        ``nu_vars[i]`` is an auxiliary Variable needed to represent the i-th AGE cone.
        The size of this variable is related to presolve behavior of ``self.ech``.

    c_vars : Dict[int, Variable]

        ``c_vars[i]`` is a Variable which determines the i-th summand in a SAGE decomposition
        of ``self.c``. The size of this variable is related to presolve behavior of ``self.ech``,
        and this can be strictly smaller than ``self.m``.

    ech : ExpCoverHelper

        A simple wrapper around the constructor argument ``covers``. Manages validation of ``covers``
        when provided, and manages construction of ``covers`` when a user does not provide it.
        This is an essential component of the duality relationship between PrimalOrdinarySageCone
        and DualOrdinarySageCone objects.
    """

    def __init__(self, c, alpha, name, covers=None):
        self.name = name
        self.alpha = alpha
        self.m = alpha.shape[0]
        self.n = alpha.shape[1]
        self.c = Expression(c)  # self.c is now definitely an ndarray of ScalarExpressions.
        self.ech = ExpCoverHelper(self.alpha, self.c, None, covers)
        self.nu_vars = dict()
        self.c_vars = dict()
        self.relent_epi_vars = dict()
        self.age_vectors = dict()
        self._variables = self.c.variables()
        self._initialize_variables()
        pass

    def _initialize_variables(self):
        if self.m > 2:
            for i in self.ech.U_I:
                nu_len = np.count_nonzero(self.ech.expcovers[i])
                if nu_len > 0:
                    nu_i = Variable(shape=(nu_len,), name='nu^{(' + str(i) + ')}_{' + self.name + '}')
                    self.nu_vars[i] = nu_i
                    epi_i = Variable(shape=(nu_len,), name='_relent_epi_^{(' + str(i) + ')}_{' + self.name + '}')
                    self.relent_epi_vars[i] = epi_i
                c_len = nu_len
                if i not in self.ech.N_I:
                    c_len += 1
                self.c_vars[i] = Variable(shape=(c_len,), name='c^{(' + str(i) + ')}_{' + self.name + '}')
            self._variables += list(self.nu_vars.values())
            self._variables += list(self.c_vars.values())
            self._variables += list(self.relent_epi_vars.values())
        pass

    def _build_aligned_age_vectors(self):
        for i in self.ech.U_I:
            ci_expr = Expression(np.zeros(self.m,))
            if i in self.ech.N_I:
                ci_expr[self.ech.expcovers[i]] = self.c_vars[i]
                ci_expr[i] = self.c[i]
            else:
                ci_expr[self.ech.expcovers[i]] = self.c_vars[i][:-1]
                ci_expr[i] = self.c_vars[i][-1]
            self.age_vectors[i] = ci_expr
        pass

    def _age_violation(self, i, norm_ord, c_i):
        if np.any(self.ech.expcovers[i]):
            idx_set = self.ech.expcovers[i]
            x_i = self.nu_vars[i].value
            x_i[x_i < 0] = 0
            y_i = np.exp(1) * c_i[idx_set]
            relent_res = np.sum(special_functions.rel_entr(x_i, y_i)) - c_i[i]  # <= 0
            relent_viol = abs(max(relent_res, 0))
            eq_res = (self.alpha[idx_set, :] - self.alpha[i, :]).T @ x_i  # == 0
            eq_res = eq_res.reshape((-1,))
            eq_viol = np.linalg.norm(eq_res, ord=norm_ord)
            total_viol = relent_viol + eq_viol
            return total_viol
        else:
            c_i = float(self.c_vars[i].value)  # >= 0
            return abs(min(0, c_i))

    def _age_vectors_sum_to_c(self):
        nonconst_locs = np.ones(self.m, dtype=bool)
        nonconst_locs[self.ech.N_I] = False
        aux_c_vars = list(self.age_vectors.values())
        aux_c_vars = aff.vstack(aux_c_vars).T
        aux_c_vars = aux_c_vars[nonconst_locs, :]
        main_c_var = self.c[nonconst_locs]
        A_vals, A_rows, A_cols, b = compiled_aff.columns_sum_leq_vec(mat=aux_c_vars, vec=main_c_var)
        K = [Cone('+', b.size)]
        return A_vals, np.array(A_rows), A_cols, b, K

    def conic_form(self):
        if self.m > 2:
            # Lift c_vars and nu_vars into Expressions of length self.m
            self._build_aligned_age_vectors()
            cone_data = []
            # age cones
            for i in self.ech.U_I:
                idx_set = self.ech.expcovers[i]
                if np.any(idx_set):
                    # relative entropy inequality constraint
                    x = self.nu_vars[i]
                    y = np.exp(1) * self.age_vectors[i][idx_set]  # This line consumes a large amount of runtime
                    z = -self.age_vectors[i][i]
                    epi = self.relent_epi_vars[i]
                    cd = sum_relent(x, y, z, epi)
                    cone_data.append(cd)
                    # linear equality constraints
                    mat = (self.alpha[idx_set, :] - self.alpha[i, :]).T
                    av, ar, ac = compiled_aff.mat_times_vecvar(mat, self.nu_vars[i])
                    num_rows = mat.shape[0]
                    curr_b = np.zeros(num_rows, )
                    curr_k = [Cone('0', num_rows)]
                    cone_data.append((av, ar, ac, curr_b, curr_k))
                else:
                    con = 0 <= self.age_vectors[i][i]
                    con.epigraph_checked = True
                    cd = con.conic_form()
                    cone_data.append(cd)
            # Vectors sum to s.c
            cone_data.append(self._age_vectors_sum_to_c())
            return cone_data
        else:
            con = self.c >= 0
            con.epigraph_checked = True
            A_vals, A_rows, A_cols, b, K = con.conic_form()
            cone_data = [(A_vals, A_rows, A_cols, b, K)]
            return cone_data

    def variables(self):
        return self._variables

    @staticmethod
    def project(item, alpha):
        if np.all(item >= 0):
            return 0
        c = Variable(shape=(item.size,))
        t = Variable(shape=(1,))
        cons = [
            vector2norm(item - c) <= t,
            PrimalOrdinarySageCone(c, alpha, 'temp_con')
        ]
        prob = Problem(CL_MIN, t, cons)
        prob.solve(verbose=False)
        return prob.value

    def violation(self, norm_ord=np.inf, rough=False):
        c = self.c.value
        if self.m > 2:
            if not rough:
                dist = PrimalOrdinarySageCone.project(c, self.alpha)
                return dist
            # compute violation for "AGE vectors sum to c"
            #   Although, we can use the fact that the SAGE cone contains R^m_++.
            #   and so only compute violation for "AGE vectors sum to <= c"
            age_vectors = {i: v.value for i, v in self.age_vectors.items()}
            sum_age_vectors = sum(age_vectors.values())
            residual = c - sum_age_vectors  # want >= 0
            residual[residual > 0] = 0
            sum_to_c_viol = np.linalg.norm(residual, ord=norm_ord)
            # compute violations for each AGE cone
            age_viols = np.zeros(shape=(len(self.ech.U_I,)))
            for idx, i in enumerate(self.ech.U_I):
                age_viols[idx] = self._age_violation(i, norm_ord, age_vectors[i])
            # add the max "AGE violation" to the violation for "AGE vectors sum to c".
            if np.any(age_viols == np.inf):
                total_viol = sum_to_c_viol + np.sum(age_viols[age_viols < np.inf])
                total_viol += PrimalOrdinarySageCone.project(c, self.alpha)
            else:
                total_viol = sum_to_c_viol + np.max(age_viols)
            return total_viol
        else:
            residual = c.reshape((-1,))  # >= 0
            residual[residual >= 0] = 0
            return np.linalg.norm(c, ord=norm_ord)
        pass
