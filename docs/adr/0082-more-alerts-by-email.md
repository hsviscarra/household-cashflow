# ADR-082: More alerts in the daily email

Status: accepted (0.91.0, Nov 2026)

Improvement plan, item D4. Hernan chose alerts by email only. ADR-078 gave the daily check-in one
kind of alert, a late statement. Four more join it, each sent once, in the same email:

| Kind | When | Sent again |
| --- | --- | --- |
| Unusual charge | A charge of the last 7 days of at least $50 and 3 times that merchant's usual (the weekly digest's rule, ADR-038) | never for that charge |
| Bill | A recurring bill due within 3 days, or late | once when due, once when late, per month |
| Budget | A group at 80% of what it has available, or over it | once at 80%, once over, per month |
| Transfer | A transfer of $500 or more, 10 to 60 days old, with no other side | never for that line |

Every kind is on by default. Data Status has an "Email alerts" card to turn kinds off
(`core.app_setting` `alerts-off`) and shows what matches right now. One kind failing is logged
and doesn't stop the others. `GET/PUT /api/alerts` read and save the choice.

Consequences: the first email after this ships can carry several lines at once, for everything
already true that day. Phone notifications wait for the phone version (plan item D3).
