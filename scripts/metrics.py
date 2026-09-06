"""Small, independently testable analytical calculations."""
import itertools
import math

def shapley_product(before, after):
    """Exact additive contribution to a multiplicative KPI, averaging all orders."""
    if before.keys() != after.keys() or not before:
        raise ValueError('Matching nonempty factor dictionaries required')
    names = list(before)
    if any(not math.isfinite(x) or x < 0 for x in [*before.values(), *after.values()]):
        raise ValueError('Factors must be finite and nonnegative')
    contributions = dict.fromkeys(names, 0.0)
    orders = list(itertools.permutations(names))
    for order in orders:
        state = before.copy()
        for name in order:
            old = math.prod(state.values()); state[name] = after[name]
            contributions[name] += (math.prod(state.values())-old)/len(orders)
    return contributions

def wilson(successes, n, z=1.959963984540054):
    """User-level binomial interval; descriptive uncertainty, not population coverage."""
    if n < 0 or not 0 <= successes <= n:
        raise ValueError('Invalid binomial counts')
    if not n: return (None, None)
    p = successes/n; den = 1+z*z/n
    center = (p+z*z/(2*n))/den
    radius = z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/den
    return (max(0,center-radius), min(1,center+radius))

def mix_decomposition(before, after):
    """Symmetric mix/within decomposition on common segment support.

    Input maps segment -> (exposure count, mean seconds). Reject missing segments
    instead of inventing an unobserved mean for entering/exiting segments.
    """
    if before.keys() != after.keys() or not before:
        raise ValueError('Common nonempty segment support required')
    n0=sum(v[0] for v in before.values());n1=sum(v[0] for v in after.values())
    if n0 <= 0 or n1 <= 0: raise ValueError('Positive exposures required')
    rows=[]
    for key in sorted(before):
        c0,m0=before[key];c1,m1=after[key];w0=c0/n0;w1=c1/n1
        rows.append({'duration_band':key, 'baseline_share':w0,'comparison_share':w1,
                     'mix_seconds':(w1-w0)*(m1+m0)/2,
                     'within_seconds':(m1-m0)*(w1+w0)/2})
    return rows
