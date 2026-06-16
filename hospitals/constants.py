"""Static configuration: the source URL, timezone, and Greek month names."""

SOURCE_URL = (
    "https://www.moh.gov.gr/articles/citizen/efhmeries-nosokomeiwn/"
    "68-efhmeries-nosokomeiwn-attikhs"
)
ATHENS_TZ = "Europe/Athens"

# Genitive-case Greek month names as they appear in the file titles
# (e.g. "17 ΙΟΥΝΙΟΥ 2026"). Accents are stripped before matching, so the
# May spelling variant (ΜΑΙΟΥ / ΜΑΪΟΥ) does not matter.
GREEK_MONTHS = {
    1: "ΙΑΝΟΥΑΡΙΟΥ",
    2: "ΦΕΒΡΟΥΑΡΙΟΥ",
    3: "ΜΑΡΤΙΟΥ",
    4: "ΑΠΡΙΛΙΟΥ",
    5: "ΜΑΙΟΥ",
    6: "ΙΟΥΝΙΟΥ",
    7: "ΙΟΥΛΙΟΥ",
    8: "ΑΥΓΟΥΣΤΟΥ",
    9: "ΣΕΠΤΕΜΒΡΙΟΥ",
    10: "ΟΚΤΩΒΡΙΟΥ",
    11: "ΝΟΕΜΒΡΙΟΥ",
    12: "ΔΕΚΕΜΒΡΙΟΥ",
}
