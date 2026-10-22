# Phase-0 capability gate report

Generated: 2026-10-22 22:52:14
Node commit: `e2d073dcd02f1e560ccb84749937138a1e184b0b`
Result: **12/12 passed**

| Gate | Result | Evidence |
|---|---|---|
| persistence across blocks | PASS | counter 1 then 2 across two later deploys (uri rho:id:yazo3i3uxz8e8hqxfipsprxetq8rsibphsnfk473dimpf7jjcety) |
| block data | PASS | reply exprs: [('ExprInt', 2714), ('ExprBytes', '04f700a417754b775d95421973bdbdadb2d23c8a5af46f1829b1431f5c136e549e8a0d61aa0c793f1a614f8e437711c7758473c6ceb0859ac7e9e07911ca66b5c4'), ('ExprInt', 1792705897197)] |
| registry insertArbitrary + lookup | PASS | lookup called the stored contract (uri rho:id:s5iz7poq7wcg7qh7ebiongqjby5ir8pt8jm4xscxws1njyxojw8y) |
| deployerId account auth | PASS | owner true, sender false (uri rho:id:d863d5uxdcsmaa8c6z98y6dhmeh8d39xr6yceu8b9wwefw8ufbty) |
| REV revFund/revRedeem round-trip | PASS | balance before=986127911404 after=986127911404; replies=[10000000, 0] |
| contract can spend presented deployerId REV (containment rationale) | PASS | contract purse=10000000; fund reply=[10000000] (uri rho:id:xthb3j86y94p4x9xry1sqewgrjfbj54dg9acsxmokcc5jax1n1to) |
| contract-held ERTP purse across blocks + burn facet | PASS | mint 10->15, burn 3, balance stays 15 (uri rho:id:oakoxfznz5wxdq8oxan81ppk4sbq7knfp866okspb9eo4jjshj3o) |
| failed deploy rolls back tuple space + native ERTP/REV | PASS | deploy failed as intended; state=[0], erp=[0], rev=[0] |
| silent deadlock / consumed state cell (documented hazard) | PASS | dead reply=[]; subsequent inc reply=[] (both empty means the cell is consumed and the deploy still commits) |
| secp256k1Verify over blake2b256 payload | PASS | valid=true, tampered=false (uri rho:id:i9m8pbnusfgw11yrybystpmpx8tn6eno97igke4m4c3rhdz1c7sy) |
| claim secret blake2b256 matches off-chain | PASS | hash 2d48cd02c18b6b89f053c61ffec5a845e7419e2e31ce9304ae7ac6abb3bd9b96 |
| measured cost + finality | PASS | install phlo=2777, call phlo=2946, block 82e51d958561… finalized=True |

A FAIL here is a stop-the-build gate, not a flaky test.
