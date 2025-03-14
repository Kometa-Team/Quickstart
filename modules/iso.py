import csv
import io

import requests

_country_url = "https://raw.githubusercontent.com/datasets/country-codes/refs/heads/main/data/country-codes.csv"
_language_url = "https://raw.githubusercontent.com/datasets/language-codes/refs/heads/main/data/language-codes-full.csv"
_tag_url = "https://raw.githubusercontent.com/datasets/language-codes/refs/heads/main/data/ietf-language-tags.csv"


def _read_csv(url):
    response = requests.get(url)
    csv_file = io.StringIO(response.text)
    return list(csv.reader(csv_file))


_tag_dict = {}
for c in _read_csv(_tag_url):
    if c[1] not in _tag_dict:
        _tag_dict[c[1]] = []
    if c[0] not in _tag_dict[c[1]]:
        _tag_dict[c[1]].append(c[0])


class Country:

    def __init__(self, data):
        self.alpha3 = data[2]
        self.alpha2 = data[9]
        self.formal = data[38]
        self.name = data[40]
        self.region = data[43]
        self.subregion = data[45]
        self.continent = data[49]
        self.languages = data[51].split(",")

    def __str__(self):
        return self.name

    def __repr__(self):
        return self.__str__()

    def __eq__(self, other):
        if isinstance(other, Country):
            return self.name == other.name
        else:
            return str(other) in [
                self.name,
                self.alpha2,
                self.alpha3,
                self.alpha2.lower(),
                self.alpha3.lower(),
            ]


class Languages:

    def __init__(self, data):
        self.alpha3 = data[0]
        self.alpha2 = data[2] if data[2] else None
        self.names = data[3].split("; ")
        self.name = self.names[0]
        if self.alpha2 in _tag_dict:
            self.tags = _tag_dict[self.alpha2]
        elif self.alpha3 in _tag_dict:
            self.tags = _tag_dict[self.alpha3]
        else:
            self.tags = []

    def __str__(self):
        return self.name

    def __repr__(self):
        return self.__str__()

    def __eq__(self, other):
        if isinstance(other, Country):
            return self.name == other.name
        else:
            return str(other) in self.names + [
                self.alpha2,
                self.alpha3,
                self.alpha2.lower(),
                self.alpha3.lower(),
            ]


countries = [Country(c) for c in _read_csv(_country_url)]
languages = [Languages(c) for c in _read_csv(_language_url)]


def get_country(name=None, alpha2=None, alpha3=None):
    if all(x is None for x in [name, alpha2, alpha3]):
        raise ValueError("Either name, alpha2, or alpha3 is required")
    for country in countries:
        if name == country.name or str(alpha2).upper() == country.alpha2 or str(alpha3).upper() == country.alpha3:
            return country
    raise NameError("No Country found")


def get_language(name=None, alpha2=None, alpha3=None):
    if all(x is None for x in [name, alpha2, alpha3]):
        raise ValueError("Either name, alpha2, or alpha3 is required")
    for language in languages:
        if name in language.names or str(alpha2).lower() == language.alpha2 or str(alpha3).lower() == language.alpha3:
            return language
    raise NameError("No Language found")
