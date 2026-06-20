from payments.models.card import CardAuthorization

def set_primary_card(card: CardAuthorization):
    CardAuthorization.objects.filter(
        user=card.user,
        primary_card=True
    ).update(primary_card=False)

    card.primary_card = True
    card.save()

def get_default_card(user):
    card = CardAuthorization.objects.filter(
        user=user,
        primary_card=True
    ).first()
    return card

