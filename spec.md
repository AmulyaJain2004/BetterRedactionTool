Assignment: PII Redaction Tool
Background
Attached is Red Herring Prospectus, document with PII information.
Task
Write a script (language of your choice) that reads the ticket log and produces a redacted version, replacing all personally identifiable information (PII) with fake alternative. For example:
Rashi Patil: John Doe
rashhi.patil@gmail.com: john.doe@example.com
Rohan Dey: Peter Parker
rohan.dey@gmail.com: peter.parker@example.com
+91 9876543210: +91 1234567645
Your solution should detect and redact, at minimum:
Full names
Email addresses
Phone numbers
Company names
Physical/mailing addresses
Social Security Numbers (SSNs)
Credit card numbers
Dates of birth
IP addresses
Deliverables
Source code for your redaction script.
The redacted output file in docx.
A short README (a few sentences) explaining your approach (e.g., regex-based, NER model, third-party library) and any tradeoffs or false positives/negatives you noticed.
Explain the evaluation approach that you have used and prepare a evaluation report for your run - include the accuracy, precision and recall numbers in the report.
Evaluation Criteria
Recall: did you catch all instances of each PII type?
Precision: did you avoid redacting things that weren't actually PII (e.g., "Order" or "Ticket" numbers, unless you choose to treat those as sensitive too; reasonable either way, just be explicit about your choice)?
Code quality: readability, structure, and how you'd extend it to a new PII type.
Communication: clarity of your README.
Time to complete: You will have 24 hours from receipt of this assignment to submit your solution. There's no single "correct" tool to use; regex, spaCy/NER, Presidio, or your own logic are all fair game.
