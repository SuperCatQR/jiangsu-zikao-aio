"""TEMPORARY throwaway test — T4 branch-protection fire proof.

This file exists only to force the `verify` check red on branch
`ci/protection-proof`, so that a real merge attempt can be made against `main`
and refused by branch protection. It is deleted with the branch; it is never
merged and never reaches `main`.
"""


def test_ci_protection_fire_proof_deliberate_failure():
    assert False, "T4 deliberate failure: branch protection fire proof"
