"""Hand-written name parts for fake companies. Each Arabic part has several real-world Latin spellings.

The spelling variants are written by hand on purpose: the matching code must not see the same
transliteration rules that produced the noise.
"""

# (Arabic, canonical English, other Latin spellings)
FAMILY_NAMES = [
    ("النور", "Al Nour", ["Alnoor", "El-Nour", "Al-Noor", "Nour"]),
    ("الحياة", "Al Hayat", ["Alhayat", "El Hayah", "Al-Hayah"]),
    ("الخطيب", "Al Khatib", ["Alkhateeb", "El-Khatib", "Khateeb"]),
    ("المصري", "Al Masri", ["Almasri", "El Masry", "Masri"]),
    ("الحسيني", "Al Husseini", ["Alhusaini", "El-Husseiny", "Husseini"]),
    ("العمري", "Al Omari", ["Alomari", "El-Omary", "Omari"]),
    ("الزعبي", "Al Zoubi", ["Alzoubi", "Al-Zubi", "Zoubi"]),
    ("الشريف", "Al Sharif", ["Alsharif", "El Sherif", "Shareef"]),
    ("القحطاني", "Al Qahtani", ["Alqahtani", "Al-Kahtani", "Qahtani"]),
    ("العتيبي", "Al Otaibi", ["Alotaibi", "Al-Otaiby", "Otaibi"]),
    ("الغامدي", "Al Ghamdi", ["Alghamdi", "Al-Ghamedi", "Ghamdi"]),
    ("الدوسري", "Al Dosari", ["Aldosari", "Al-Dossary", "Dossari"]),
    ("الحربي", "Al Harbi", ["Alharbi", "Al-Harby", "Harbi"]),
    ("الشمري", "Al Shammari", ["Alshammari", "Al-Shamari", "Shammari"]),
    ("المالكي", "Al Maliki", ["Almaliki", "Al-Malki", "Malki"]),
    ("الرفاعي", "Al Rifai", ["Alrifai", "Al-Refaie", "Rifai"]),
    ("الطراونة", "Al Tarawneh", ["Altarawneh", "Tarawneh", "Al-Tarawna"]),
    ("المجالي", "Al Majali", ["Almajali", "Majali", "Al-Majaly"]),
    ("العبادي", "Al Abbadi", ["Alabbadi", "Abbadi", "Al-Abadi"]),
    ("الفايز", "Al Fayez", ["Alfayez", "Fayez", "Al-Faiz"]),
    ("الروابدة", "Al Rawabdeh", ["Alrawabdeh", "Rawabdeh"]),
    ("البدور", "Al Bdour", ["Albdour", "Bdour", "Al-Bdoor"]),
    ("الصفدي", "Al Safadi", ["Alsafadi", "Safadi", "El-Safady"]),
    ("الكيلاني", "Al Kilani", ["Alkilani", "Kilany", "Al-Keilani"]),
    ("الأمل", "Al Amal", ["Alamal", "El-Amal", "Amal"]),
    ("الفجر", "Al Fajr", ["Alfajr", "El-Fajer", "Fajer"]),
    ("الرواد", "Al Rowad", ["Alrowad", "Al-Ruwad", "Rowad"]),
    ("الأفق", "Al Ofoq", ["Alofoq", "Al-Ufuq", "Ofuq"]),
    ("الواحة", "Al Waha", ["Alwaha", "Al-Wahah", "Oasis"]),
    ("السلام", "Al Salam", ["Alsalam", "El-Salam", "Salam"]),
    ("الهدى", "Al Huda", ["Alhuda", "El-Hoda", "Huda"]),
    ("الريان", "Al Rayyan", ["Alrayyan", "Al-Rayan", "Rayan"]),
    ("البركة", "Al Baraka", ["Albaraka", "Al-Barakah", "Baraka"]),
    ("النخبة", "Al Nukhba", ["Alnukhba", "Al-Nokhba", "Elite"]),
    ("الصقر", "Al Saqr", ["Alsaqr", "Al-Saker", "Saqer"]),
    ("الجزيرة", "Al Jazeera", ["Aljazeera", "Al-Jazira", "Jazira"]),
]

FIRST_NAMES = [
    ("محمد", "Mohammad", ["Mohammed", "Muhammad", "Mohamad", "MHD"]),
    ("أحمد", "Ahmad", ["Ahmed", "Ahmd"]),
    ("خالد", "Khaled", ["Khalid", "Khald"]),
    ("عبدالله", "Abdullah", ["Abdallah", "Abdulla"]),
    ("يوسف", "Yousef", ["Yusuf", "Youssef"]),
    ("فيصل", "Faisal", ["Faysal", "Feisal"]),
    ("سامي", "Sami", ["Samy", "Sammy"]),
    ("عمر", "Omar", ["Umar", "Omer"]),
]

# (Arabic phrase as written after the family name, English word)
ACTIVITIES = [
    ("للتجارة", "Trading"),
    ("للمقاولات", "Contracting"),
    ("للأدوية", "Pharma"),
    ("للصناعات الغذائية", "Food Industries"),
    ("للتكنولوجيا", "Technology"),
    ("للسياحة والسفر", "Tourism and Travel"),
    ("للخدمات اللوجستية", "Logistics Services"),
    ("للاستشارات الهندسية", "Engineering Consulting"),
    ("للطباعة والنشر", "Printing and Publishing"),
    ("للأثاث", "Furniture"),
    ("للإلكترونيات", "Electronics"),
    ("للعقارات", "Real Estate"),
    ("للنقل", "Transport"),
    ("للمستلزمات الطبية", "Medical Supplies"),
]

# (Arabic legal form, English legal form)
COMPANY_FORMS = [("شركة", "Co."), ("مؤسسة", "Est."), ("مجموعة", "Group")]
