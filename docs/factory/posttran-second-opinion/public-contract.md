# Public POSTTRAN contract

Implement pinned CBTRN02C and its copybooks in Java 21. Use only supplied public
source, copybooks, this contract and before images. Preserve fixed-width records,
signed zoned amounts, numeric scale, source control flow and file status behavior.
Entry point: `PosttranCandidate INPUT_DIRECTORY OUTPUT_DIRECTORY CURRENT_DATE`.
Read ACCTFILE, TCATBALF, XREFFILE, TRANFILE and DALYTRAN before images. Write
updated ACCTFILE, TCATBALF, TRANFILE and DALYREJS images with newline-separated
fixed-width ASCII transport records and the source return code. Do not change
the supplied inputs. CURRENT_DATE is an explicit declared scenario clock.
No network, shell, filesystem reads outside the input directory, or dependencies
outside the JDK. No expected output is supplied. Do not consult other candidates,
the twin, test implementation, reviews, receipts or repository history.
