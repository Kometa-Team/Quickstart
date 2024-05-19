
import iso639
import iso3166

def validate_iso3166_1(code):
    try:
        country = iso3166.countries.get(code.upper())
        if country:
            return country.alpha2
        else:
            return None
    except KeyError:
        return None


def validate_iso639_1(code):
    if len(code) == 2 and iso639.languages.get(alpha2=code.lower()):
        return code.lower()
    return None
