
from .models import TokenWallet


def token_balance(request):
    if request.user.is_authenticated:
        try:
            wallet = TokenWallet.objects.get(tenant=request.user)
            return {'token_balance': wallet.tokens}
        except TokenWallet.DoesNotExist:
            return {'token_balance': 0}
    return {}
