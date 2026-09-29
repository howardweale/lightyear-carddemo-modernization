"""Distinct purchasing register version; historical register remains immutable."""
from lightyear_calibration.ms94_v3_rules import validate_register as validate_rules
from lightyear_calibration.contracts import require


def validate_register(register, inventory, assessed_on):
    require(register.get('scope_change_decision',{}).get('status') in ('proposed','approved'),
            'Purchasing scope decision is missing')
    # A proposed rule may be assessed by test equipment. It is not a signed
    # human decision, and the final source-review gate must still approve it.
    return validate_rules(register,inventory,assessed_on)
