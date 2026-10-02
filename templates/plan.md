# Plan template (run/tickets/MMA-XXXX/plan.md)
# The reference's structure (design doc §3.3 + §9.2), with two additions.
#
# ## Scope + deps
# - **Module:** :core:ui
# - **Deps:** T-01, T-03 (must be merged before work starts)
# - **Covers:** R11, R11.1, R11.2, R11.3
#
# ## Module / file table
# | File | Change | Notes |
# |---|---|---|
# | core/ui/src/.../nav3/scene/... | new | |
#
# ## Requirement -> implementation map
# | Req | Artifact | Status |
# |---|---|---|
# | R11 | nav3 scene strategy | planned |
#
# ## Contracts verified (with source)
# | Contract | Confirmed in | How |
# |---|---|---|
# | Navigation3Scene 1.1.6 | navigation3-ui bytecode | `javap -c ...` |
#
# ## Design-vs-API deviations to flag in PR
# 1.
# 2.
#
# ## Test strategy
# - **Surface:** nav3 scene renders at 0/90/135°
# - **Harness:** jvmTest in navigation3-ui
# - **Asserts:** layout bounds equal expected
#
# ## Definition-of-Done -> gates mapping
# | Gate | Command |
# |---|---|
# | unit | ./verify.sh --inner --module :core:ui |
# | integration | ./gradlew :core:ui:test |
#
# ## Cost / round budget
# - code: 0/3, test: 0/3, response: 0/5
# - target: < 60000 tokens, < $5.00
#
# ## Traceability
# This plan proves R11, R11.1, R11.2, R11.3.
