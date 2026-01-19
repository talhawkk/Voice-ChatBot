"""
Language detection utility.
Detects language from text using character set scoring + Roman Urdu/Hindi word detection.
Supports: English, Urdu, Hindi
"""
from typing import Set


def detect_text_language(text: str) -> str:
    """
    Detect language from text using character set scoring + Roman Urdu/Hindi word detection.
    Returns: 'en', 'ur', 'hi', or 'en' as default
    
    Handles:
    - Native scripts (Arabic for Urdu, Devanagari for Hindi)
    - Roman Urdu (Urdu words written in Latin script like "kia haal hai")
    - Roman Hindi (Hindi words written in Latin script)
    """
    if not text or len(text.strip()) == 0:
        return "en"
    
    text_clean = text.strip().lower()
    words = text_clean.split()
    
    # Urdu character set (Arabic script used in Urdu) - extended set
    urdu_chars: Set[str] = set("ءآأؤإئابتثجحخدذرزسشصضطظعغفقكلمنهوىي۰۱۲۳۴۵۶۷۸۹")
    
    # Hindi character set (Devanagari script) - extended set
    hindi_chars: Set[str] = set("अआइईउऊएऐओऔऋकखगघचछजझटठडढणतथदधनपफबभमयरलवशषसह०१२३४५६७८९")
    
    # Common Roman Urdu words (Urdu written in Latin script) - Expanded
    roman_urdu_words: Set[str] = {
        # Question words
        "kia", "kya", "kaisa", "kese", "kaise", "kyun", "kyu", "kab", "kahan", "kis", "kaun",
        # Common verbs
        "haal", "hal", "tumhara", "tumhari", "tumharay", "tum", "aap", "apka", "apki",
        "mein", "main", "hain", "hai", "ho", "hona", "hoga", "hogi", "thay", "the",
        "nahi", "nhi", "na", "bhi", "se", "ke", "ka", "ki", "ko", "par", "pe",
        "aur", "or", "ya", "yaa", "toh", "to", "tha", "thi", "raha", "rahi", "rahe",
        "chahiye", "chahye", "karna", "kare", "karo", "karein", "bolo", "bol", "batao",
        "achha", "acha", "theek", "thik", "theak", "bilkul", "zaroor", "zror",
        "sab", "sabse", "sabko", "sabka", "sabki",
        # Pronouns and possessives
        "tumhara", "tumhari", "mera", "meri", "mere", "hamara", "hamari", "hamare", "uska", "uski", "uske",
        "yeh", "ye", "woh", "wo", "is", "us", "in", "un", "inke", "unke", "iski", "uski",
        # Common words
        "kuch", "kuchh", "bahut", "bohat", "zyada", "zada", "kam", "kum",
        "kahan", "yahan", "wahan", "jahan",
        # Time/actions
        "abhi", "ab", "pehle", "baad", "phir", "fir",
        "sunao", "batao", "bolo", "kaho", "kar", "karo", "kare",
        # Common phrases
        "kya haal hai", "kese ho", "kaise ho", "kya kar rahe ho", "kya kar raha hai"
    }
    
    # Common Roman Hindi words
    roman_hindi_words: Set[str] = {
        "kaisa", "kaise", "kyun", "kab", "kahan", "kis", "kaun", "kya",
        "hal", "tumhara", "tumhari", "tum", "aap", "apka", "apki",
        "main", "hain", "hai", "ho", "hona", "hoga", "hogi", "the", "thay",
        "nahi", "nhi", "na", "bhi", "se", "ke", "ka", "ki", "ko", "par", "pe",
        "aur", "ya", "toh", "to", "tha", "thi", "raha", "rahi", "rahe",
        "chahiye", "karna", "kare", "karo", "batao", "bolo",
        "achha", "thik", "bilkul", "sab", "mera", "meri", "uska", "uski"
    }
    
    # Count characters for each language
    total_chars = len([c for c in text_clean if c.isalnum() or c in urdu_chars or c in hindi_chars])
    
    urdu_count = sum(1 for c in text_clean if c in urdu_chars)
    hindi_count = sum(1 for c in text_clean if c in hindi_chars)
    
    # Calculate percentages for native scripts
    urdu_percent = (urdu_count / total_chars) * 100 if total_chars > 0 else 0
    hindi_percent = (hindi_count / total_chars) * 100 if total_chars > 0 else 0
    
    # Count Roman Urdu/Hindi words
    roman_urdu_count = sum(1 for word in words if word in roman_urdu_words)
    roman_hindi_count = sum(1 for word in words if word in roman_hindi_words)
    
    # Calculate Roman word percentages
    total_words = len(words) if words else 1
    roman_urdu_percent = (roman_urdu_count / total_words) * 100
    roman_hindi_percent = (roman_hindi_count / total_words) * 100
    
    # Thresholds
    script_threshold = 20.0  # For native scripts
    roman_threshold = 25.0   # For Roman Urdu/Hindi
    
    # Scoring system
    urdu_score = urdu_percent + (roman_urdu_percent * 0.5)  # Native script weighted higher
    hindi_score = hindi_percent + (roman_hindi_percent * 0.5)
    
    # Decision logic
    if urdu_score >= script_threshold or roman_urdu_percent >= roman_threshold:
        return "ur"
    elif hindi_score >= script_threshold or roman_hindi_percent >= roman_threshold:
        return "hi"
    else:
        return "en"
