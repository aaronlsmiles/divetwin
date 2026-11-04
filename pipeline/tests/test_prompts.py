import hashlib

from prompts import PROMPTS

SHA256 = {
    "D": "a56569ed118ea76b3578c33154971808bfa70a4b97982d4c1fe02202b5e3672e",
    "B": "21aee7e5b9d51d6cd720c2ddf84ee32fe16c10f7145aff672e4e2f9a0973ca54",
    "N": "e1477c868fcefc86e948af9ee517f2bdb776e51aa2439d61e6776b692602c31f",
}


def test_prompts_frozen():
    for k, want in SHA256.items():
        assert hashlib.sha256(PROMPTS[k].encode()).hexdigest() == want, f"prompt {k} was edited"
