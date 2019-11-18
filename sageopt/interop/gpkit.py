from sageopt.symbolic.signomials import Signomial

try:
    from gpkit import SignomialsEnabled
    from gpkit.nomials import SignomialInequality, PosynomialInequality
    from gpkit.nomials import SingleSignomialEquality, MonomialEquality
except ImportError:
    pass


def gpkit_hmap_to_sageopt_sig(curhmap, vkmap):
    n_vks = len(vkmap)
    temp_sig_dict = dict()
    for expinfo, coeff in curhmap.items():
        tup = n_vks * [0]
        for vk, expval in expinfo.items():
            tup[vkmap[vk]] = expval
        temp_sig_dict[tuple(tup)] = coeff
    s = Signomial(temp_sig_dict)
    return s


def _gp_con_hmap(con, subs):
    exprlist = con.as_posyslt1()
    if len(exprlist) == 0:
        return None
    else:
        hmap = exprlist[0].sub(subs).hmap
        return hmap


def _sp_eq_con_hmap(con, subs):
    expr = con.right - con.left
    hmap = expr.sub(subs).hmap
    return hmap


def _sp_ineq_con_hmap(con, subs):
    gtzero_rep = (con.right - con.left) * (1. - 2 * (con.oper == '>='))
    hmap = gtzero_rep.sub(subs).hmap
    return hmap


def gpkit_model_to_sageopt_model(gpk_mod):
    subs = gpk_mod.substitutions
    constraints = [con for con in gpk_mod.flat(constraintsets=False)]
    varkeys = sorted([vk for vk in gpk_mod.varkeys if vk not in subs], key=lambda vk: vk.name)
    vkmap = {vk: i for (i, vk) in enumerate(varkeys)}
    # construct sageopt Signomial objects for each GPKit constraint
    gp_eqs, gp_gts, sp_eqs, sp_gts = [], [], [], []
    for i, constraint in enumerate(constraints):
        if isinstance(constraint, MonomialEquality):
            hmap = _gp_con_hmap(constraint, subs)
            if hmap is not None:
                cursig = 1 - gpkit_hmap_to_sageopt_sig(hmap, vkmap)
                cursig.metadata['GPKit constraint index'] = i
                gp_eqs.append(cursig)
        elif isinstance(constraint, PosynomialInequality):
            hmap = _gp_con_hmap(constraint, subs)
            if hmap is not None:
                cursig = 1 - gpkit_hmap_to_sageopt_sig(hmap, vkmap)
                cursig.metadata['GPKit constraint index'] = i
                gp_gts.append(cursig)
        elif isinstance(constraint, SignomialInequality):
            # ^ incidentally, these can also be equality constraints
            with SignomialsEnabled():
                if isinstance(constraint, SingleSignomialEquality):
                    hmap = _sp_eq_con_hmap(constraint, subs)
                    cursig = gpkit_hmap_to_sageopt_sig(hmap, vkmap)
                    cursig.metadata['GPKit constraint index'] = i
                    sp_eqs.append(cursig)
                else:
                    hmap = _sp_ineq_con_hmap(constraint, subs)
                    cursig = gpkit_hmap_to_sageopt_sig(hmap, vkmap)
                    cursig.metadata['GPKit constraint index'] = i
                    sp_gts.append(cursig)
    # Build a sageopt Signomial from the GPKit objective.
    f = gpkit_hmap_to_sageopt_sig(gpk_mod.cost.hmap, vkmap)  # should this have a substitution applied first?
    # Somehow aggregate all sageopt problem data. Might make a class for this later.
    so_mod = {
        'f': f,
        'gp_eqs': gp_eqs,
        'sp_eqs': sp_eqs,
        'gp_gts': gp_gts,
        'sp_gts': sp_gts,
        'vkmap': vkmap
    }
    return so_mod
