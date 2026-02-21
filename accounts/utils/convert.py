import pycountry

def get_country_name(code):
    c = pycountry.countries.get(alpha_2=code)
    return c.name if c else code