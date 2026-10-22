# Pricing Recommendation: Online Retail II

**To:** Pricing Manager  **Data:** ~1.0M cleaned order lines, UK online retailer, Dec 2009 – Dec 2011
**Scope:** Retail-size order lines (24 units or fewer). Wholesale-size lines are excluded from elasticity and sizing.

## Bottom line
Pricing is a **modest but real lever** (about **+$51K a year, roughly 1.8% of estimated retail-size profit**). The clearest wins are to **raise prices on products with low price sensitivity** and to **stop deep clearance discounting**, which sold units but lost money.

## Three actions

### 1. Raise prices ~5% on low-sensitivity products
- **1,263 products** have demand that is not sensitive enough to price for a rise to hurt profit (|elasticity| below 2.5 at the assumed 40% margin).
- **690 of them are high-confidence** (the whole 95% interval stays under the threshold); start there.
- Estimated impact: **+$47.6K/yr** for all 1,263 (**+$34.7K/yr** from the 690 high-confidence ones).
- Examples of high-confidence candidates: Vintage Red Kitchen Cabinet (elasticity -0.77), Victorian Sewing Box Large (-0.71), Set of 3 Cake Tins Pantry Design (-1.42).
- Roll out by category and track units for 4-6 weeks against a held-out comparison group.

### 2. Cap promo depth at roughly 30%
| Depth | Products | Profit-positive | Net profit (assumed cost) |
|---|---|---|---|
| Shallow (15-30% off) | 163 | 66% | **+$22K** |
| Medium (30-40%) | 81 | 40% | -$1K |
| Deep clearance (>40%) | 487 | 3% | **-$132K** |

- Shallow promos showed **no post-promo demand dip**. Deep clearance pulled forward about 14% of demand in the following four weeks.
- Treat deep markdowns as an explicit inventory decision (write-off vs. clearance), not as a marketing promo.

### 3. Discount only a small, specific set
- Just **38 products** are clearly price-sensitive enough (|elasticity| above 2.5) for a cut to raise profit, worth about **+$3K/yr**. This is a minor opportunity; don't build a program around it.

## How reliable is this?
| Issue | Effect | What I did |
|---|---|---|
| **Bulk-discount bias:** revenue ÷ quantity makes big discounted orders look like price sensitivity | Naive median elasticity -2.63 vs robust **-1.96** (~25% overstated) | Used list price on small orders only |
| **Cost is assumed**, not in the data (60% of price) | Raise group is 922 / 1,263 / 1,563 products at 50% / 60% / 70% cost; discount group 62 / 38 / 6 | Showed sensitivity; **replace with real unit costs before acting** |
| **Prices weren't randomly set**; changes coincide with stock clearance and seasons | Elasticities are correlations; 79.5% of products come out "significant," which is high | Month fixed effects, agreement filter between methods; **run a price test to confirm** |
| **Promos are inferred** (no promo flag): week at least 15% below the product's median price | Deep "promos" are mostly clearance of low-volume items, so lifts (median +508%) come from tiny baselines | Split results by depth; don't quote the median lift |
| Method agreement is moderate (correlation 0.64 across products) | Individual product numbers are noisy | Trust segment-level results over any single product |

## Next steps
1. Get real unit costs and rerun the segmentation (changes group sizes, not the method).
2. A/B test a 5% rise on 50-100 high-confidence products with a matched control group for 6 weeks.
3. Set a promo depth guideline (about 30% max) and require a stock reason for anything deeper.
4. Extend to wholesale lines separately; they behave differently and were excluded here.

*Reproduce: `src/01_load_clean.py` → `02_elasticity.py` → `03_promo_segments.py` → `04_charts.py`. Charts in `outputs/charts/`.*
