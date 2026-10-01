"""The master list of real PII this document actually contains, compiled
by hand from a full read-through of the director/promoter/KMP tables, the
"Contact Person" fields of every banker/advisor listing, and a keyword
sweep for company-suffix words (Limited, Bank, LLP, Trust, ...).

This is the ground truth's source of truth for PERSON and ORGANIZATION:
build_ground_truth.py finds every occurrence of every name below in the
document text. Longer names are listed before names they contain (e.g.
"Rajesh Kushal Hegde" before a bare "Hegde") is not needed here because,
verified during compilation, no informal partial-name variants exist in
this document -- every mention uses the same full form.
"""

# Real individuals: directors, promoters, KMPs/senior management, and the
# named contact person at every bank/underwriter/advisor listed.
KNOWN_PERSON_NAMES = [
    "Kushal Subbayya Hegde",
    "Rajesh Kushal Hegde",
    "Rohit Kushal Hegde",
    "Rakhi Girija Shetty",
    "Dinesh Hirachand Munot",
    "Ajay Shriram Patil",
    "Ram Kumar Tiwari",
    "Indu Jacob",
    "Pushpa Kushal Hegde",
    "Sandesh Bhagwat",
    "Amod Joshi",
    "Ganesh Prasad",
    "Sarthak Malvadkar",
    "Prakash Boricha",
    "Shanti Gopalkrishnan",
    "Eric Bacha",
    "Sachin Gawade",
    "Pravin Teli",
    "Siddharth Jadhav",
    "Tushar Gavankar",
    "Varun Badai",
    "Hitesh Ramani",
    "Chitra Raste",
    "Sharmila Joshi",
    "Cherag Gyara",
    "Manisha Shukla",
    "Tushar Wakhele",
    "Ashish Mathew Pulloor",
    "Anand Soni",
    "Lokesh Shah",
    "Soumavo Sarkar",
    "Kishan Rastogi",
    "Abhijit Diwan",
    # ALL-CAPS variants: this document has one running-header line that
    # spells out all Promoter names in capitals ("OUR PROMOTERS: KUSHAL
    # SUBBAYYA HEGDE, ..."), which is easy for a human to miss too.
    "KUSHAL SUBBAYYA HEGDE",
    "PUSHPA KUSHAL HEGDE",
    "RAJESH KUSHAL HEGDE",
    "ROHIT KUSHAL HEGDE",
    "RAKHI GIRIJA SHETTY",
    # Family members and historical shareholders, found in the corporate
    # history / capital structure / share-transfer sections. These use
    # informal short forms (no middle name) that don't overlap the fuller
    # forms above, so both need listing.
    "Maithili Rajesh Hegde",
    "Katyayani Balasubramanian",
    "Karunakar N. Bhandary",
    "Narayna B. Shetty",
    "Jayaram N. Shetty",
    "Karunakar Hegde",
    "Vijay Hegde",
    "Kushal Hegde",
    "Rajesh Hegde",
    "Rohit Hegde",
    "Pushpa Hegde",
]

# Real, specific commercial/legal entities -- the issuer, its promoter
# entities, its subsidiaries/group companies, banks, underwriters, law
# firm, auditors, and peer companies cited for benchmarking. Generic
# regulator/statute names and placeholder roles ("Sponsor Bank", "Escrow
# Collection Bank") are intentionally excluded -- see README "Company
# scope" for why, and config/org_exclude_list.txt for the deny-list.
KNOWN_ORGANIZATION_NAMES = [
    "KSH International Limited",
    "KSH INTERNATIONAL LIMITED",
    "KSH International Private Limited",
    "Bhandary Metal Extrusion Private Limited",
    "CARE Analytics and Advisory Private Limited",
    "Care Analytics and Advisory Private Limited",
    "Al-Ahleia Switchgear Co.",
    "Bharat Bijlee Limited",
    "CG Power and Industrial Solutions Limited",
    "Emirates Transformer & Switchgear Limited",
    "Nidec Industrial Automation India Private Limited",
    "Elantas Beck India Limited",
    "Hindalco Industries Limited",
    "Polycom Associates",
    "Savli Copper Products Private Limited",
    "Vedanta Limited",
    "Georgia Transformer Corporation",
    "Virginia Transformer Corporation",
    "Transformers & Rectifiers (India) Limited",
    "Ahlstrom Sweden AB",
    "Cindus Corporation",
    "Union Copper Rod LLC",
    "KSH International Chakan Internal Kamgar Sangathna",
    "I-Sec",
    "Kanj and Co LLP",
    "Kanj & Co. LLP",
    "CARE Ratings Limited",
    "Care Ratings Limited",
    "Waterloo Motors Private Limited",
    "KSH Project Management Services Private Limited",
    "KSH Infra Park VI Private Limited",
    "KSH Infra Park IV Private Limited",
    "KSH Distriparks Private Limited",
    "KSH Integrated Logistics Private Limited",
    "Kushal Motors and Electricals Private Limited",
    "Waterloo Industrial Park IX A Private Limited",
    "Waterloo Industrial Park IX B Private Limited",
    "Waterloo Industrial Park IX Private Limited",
    "Waterloo Industrial Park VIII Private Limited",
    "Waterloo Industrial Park VI Private Limited",
    "Waterloo Industrial Park V Private Limited",
    "Waterloo Industrial Park IV Private Limited",
    "Waterloo Industrial Park III Private Limited",
    "Waterloo Industrial Park II Private Limited",
    "Waterloo Industrial Park I Private Limited",
    "Nuvama Wealth Management Limited",
    "ICICI Securities Limited",
    "MUFG Intime India Private Limited",
    "Link Intime India Private Limited",
    "HDFC Bank Limited",
    "ICICI Bank Limited",
    "IndusInd Bank Limited",
    "The Federal Bank Limited",
    "Bajaj Finance Limited",
    "Kirtane & Pandit, LLP",
    "Kirtane & Pandit LLP",
    "Hingne Tare & Associates",
    "Trilegal",
    "Precision Wires India Limited",
    "Solar Energy Corporation of India Limited",
    "Malabar India Fund Limited",
    "Shubhkamal Leasing and Investment Private Limited",
    "Dhaulagiri Family Trust",
    "Everest Family Trust",
    "Makalu Family Trust",
    "Broad Family Trust",
    "Annapurna Family Trust",
    "Kanchenjunga Family Trust",
    "Loksatta",
    "Financial Express",
    # ALL-CAPS variants (see the matching comment in KNOWN_PERSON_NAMES).
    "DHAULAGIRI FAMILY TRUST",
    "EVEREST FAMILY TRUST",
    "MAKALU FAMILY TRUST",
    "BROAD FAMILY TRUST",
    "ANNAPURNA FAMILY TRUST",
    "KANCHENJUNGA FAMILY TRUST",
    "WATERLOO INDUSTRIAL PARK VI PRIVATE LIMITED",
]
