"""How games earn coins for the Art shop. Product settings, in one place (docs/art-shop.md).

Coins are given once for a finished game round, never for using the camera, blinking
more, reporting symptoms or skipping breaks. Keyboard play earns exactly the same as
playing with the eyes. A daily limit keeps the shop from becoming a reason to stay
at the screen: a few short rounds a day reach it, and playing longer earns nothing more.

    Blink Code   a finished 90-second challenge with at least one word spelled:
                 10 coins + 1 per 25 points, at most 40
    EyeGame      a finished run of at least 50 points:
                 5 coins + 1 per 40 points, at most 30
    Daily limit  150 coins a day from all games together

Practice modes (Blink Code's Learn and Free blink) earn nothing: they have no end.
"""

DAILY_GAME_COIN_LIMIT = 150

BLINK_CODE_BASE, BLINK_CODE_PER_POINTS, BLINK_CODE_MAX = 10, 25, 40
EYE_GAME_MIN_SCORE, EYE_GAME_BASE, EYE_GAME_PER_POINTS, EYE_GAME_MAX = 50, 5, 40, 30


def blink_code_coins(score: int, words_done: int) -> int:
    if words_done < 1 or score <= 0:
        return 0
    return min(BLINK_CODE_MAX, BLINK_CODE_BASE + score // BLINK_CODE_PER_POINTS)


def eye_game_coins(score: int) -> int:
    if score < EYE_GAME_MIN_SCORE:
        return 0
    return min(EYE_GAME_MAX, EYE_GAME_BASE + score // EYE_GAME_PER_POINTS)
