identification division.
program-id. probe.
data division.
working-storage section.
01 bal pic s9(09)v99.
01 rate-value pic s9(04)v99.
01 interest-value pic s9(09)v99.
procedure division.
 move 250.75 to bal
 move 21.00 to rate-value
 compute interest-value = (bal * rate-value) / 1200
 if interest-value not = 4.38 stop run returning 11 end-if
 move -250.75 to bal
 compute interest-value = (bal * rate-value) / 1200
 if interest-value not = -4.38 stop run returning 12 end-if
 move 999999999.99 to bal
 move 9999.99 to rate-value
 compute interest-value = (bal * rate-value) / 1200
 if interest-value not = 333324999.91 stop run returning 13 end-if
 stop run returning 0.
