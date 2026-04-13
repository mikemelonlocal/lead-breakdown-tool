"""
Constants for Lead Analyzer — Melon Local.
Color palettes, thresholds, UTM tokens, platform rules.
"""

# ========== 3. CONSTANTS ==========

# Brand Colors (Melon Local Design System)
PINE_GREEN = '#114e38'        # Primary dark (Pine - TERTIARY)
CACTUS_GREEN = '#47B74F'      # Primary bright (Cactus - PRIMARY)
LEMON_SUN = '#F1CB20'         # Accent yellow (Lemon Sun - PRIMARY)

# Complete Official Melon Local Color Palette from Brand Book (March 2023, Page 13)
# PRIMARY COLORS
ALPINE = '#FEF8E9'           # C0 M2 Y9 K0
CACTUS = '#47B74F'           # C72 M0 Y95 K0 (PRIMARY)
LEMON_SUN_OFFICIAL = '#F1CB20'  # C5 M20 Y100 K0 (PRIMARY)

# SECONDARY COLORS
SAND = '#EDDFDB'             # C7 M9 Y28 K0
CLOVER = '#40A74C'           # C85 M5 Y100 K0
MUSTARD_SEED = '#CC8F15'     # C15 M45 Y100 K0
WATERMELON_SUGAR = '#E9736E' # C0 M75 Y50 K0
WHITNEY_PINK = '#FF9B94'     # C0 M54 Y30 K0

# TERTIARY COLORS
MOJAVE = '#CFBA97'           # C20 M25 Y42 K0
PINE = '#114e38'             # C95 M40 Y85 K45 (TERTIARY)
COCONUT = '#644414'          # C42 M65 Y100 K40
CRANBERRY = '#6C2126'        # C32 M96 Y80 K40

# Extended Melon Local color palette for charts - OPTIMIZED FOR CONTRAST
MELON_COLORS = {
    # Main palette - maximum contrast between adjacent colors
    # Pattern: Green → Yellow → Red/Pink → Brown → Green (alternating color families)
    'primary': [
        '#47B74F',  # 1. Cactus (bright green)
        '#F1CB20',  # 2. Lemon Sun (yellow) - contrast with green
        '#E9736E',  # 3. Watermelon Sugar (coral) - contrast with yellow
        '#114e38',  # 4. Pine (dark green) - contrast with coral
        '#CC8F15',  # 5. Mustard Seed (gold) - contrast with dark green
        '#FF9B94',  # 6. Whitney Pink (pink) - contrast with gold
        '#40A74C',  # 7. Clover (mid green) - contrast with pink
        '#6C2126',  # 8. Cranberry (burgundy) - contrast with green
        '#CFBA97',  # 9. Mojave (tan) - contrast with burgundy
        '#644414'   # 10. Coconut (brown) - contrast with tan
    ],
    # Legacy palette - darker tones with high contrast
    'legacy': [
        '#114e38',  # 1. Pine (dark green)
        '#F1CB20',  # 2. Lemon Sun (yellow) - contrast
        '#6C2126',  # 3. Cranberry (burgundy) - contrast
        '#47B74F',  # 4. Cactus (bright green) - contrast
        '#CC8F15',  # 5. Mustard Seed (gold) - contrast
        '#E9736E',  # 6. Watermelon Sugar (coral) - contrast
        '#40A74C',  # 7. Clover (mid green) - contrast
        '#CFBA97',  # 8. Mojave (tan) - contrast
        '#644414'   # 9. Coconut (brown) - contrast
    ],
    # MOA palette - bright tones with high contrast
    'moa': [
        '#47B74F',  # 1. Cactus (bright green)
        '#F1CB20',  # 2. Lemon Sun (yellow) - contrast
        '#FF9B94',  # 3. Whitney Pink (pink) - contrast
        '#40A74C',  # 4. Clover (mid green) - contrast
        '#CC8F15',  # 5. Mustard Seed (gold) - contrast
        '#E9736E',  # 6. Watermelon Sugar (coral) - contrast
        '#114e38',  # 7. Pine (dark green) - contrast
        '#CFBA97',  # 8. Mojave (tan) - contrast
        '#6C2126'   # 9. Cranberry (burgundy) - contrast
    ],
    # Contrast palette - alternating warm/cool colors
    'contrast': [
        '#47B74F',  # 1. Cactus (cool green)
        '#CC8F15',  # 2. Mustard Seed (warm gold) - contrast
        '#114e38',  # 3. Pine (cool dark green) - contrast
        '#E9736E',  # 4. Watermelon Sugar (warm coral) - contrast
        '#40A74C',  # 5. Clover (cool mid green) - contrast
        '#F1CB20',  # 6. Lemon Sun (warm yellow) - contrast
        '#6C2126',  # 7. Cranberry (cool burgundy) - contrast
        '#FF9B94',  # 8. Whitney Pink (warm pink) - contrast
        '#CFBA97'   # 9. Mojave (neutral tan) - contrast
    ]
}

# ============================================================================
# ADS ACCOUNT HEALTH - CONSTANTS
# ============================================================================
# Ads Account Health Thresholds
ADS_THRESHOLDS = {
    'target_top_is_min': 0.60,           # 60% minimum for top positions
    'target_top_is_max': 0.80,           # 80% maximum for top positions
    'target_abs_top_is_min': 0.20,       # 20% minimum position 1
    'target_abs_top_is_max': 0.40,       # 40% maximum position 1
    'increase_lost_is_rank_min': 0.30,   # 30% lost to rank triggers increase
    'decrease_abs_top_is_min': 0.50,     # 50% abs top triggers decrease
    'poor_ctr_threshold': 0.015,         # 1.5% CTR is poor
    'good_ctr_threshold': 0.04,          # 4% CTR is good
    'low_impr_share_threshold': 0.30,    # 30% impr share is low
    'min_spend_threshold': 20.0,         # $20 minimum spend to flag
}


ALPINE_CREAM = '#f2f0e6'      # Background light
WHITE = '#ffffff'
TEXT_DARK = '#171717'
TEXT_LIGHT = '#666666'

# Analysis Parameters
CONSERVATIVE_CPL_THRESHOLD = 25.0
CONSERVATIVE_DAMPING_FACTOR = 0.6
CONSERVATIVE_EFFICIENCY_WEIGHT = 0.7
CONSERVATIVE_SPEND_WEIGHT = 0.3
ALLOCATION_ROUNDING_INCREMENT = 5

# UTM Tokens for Campaign Classification
UTM_TOKENS_FIXED = [
    "001", "003", "004", "005", "0055", "119", "120", "170",
    "171", "172", "173", "PPR", "PPA", "PPH", "PPC", "271", "273", "205",
    # Melon Max device codes
    "AM", "AT", "AD",  # Auto Mobile, Auto Tablet, Auto Desktop
    "HM", "HT", "HD",  # Home Mobile, Home Tablet, Home Desktop
    # Listings
    "MLLIST"
]

# Platform Classification Rules
PLATFORM_RULES = {
    'melon_max_prefix': 'QS',
    'microsoft_campaigns': ['MLB', 'MLSB'],
    'google_campaigns': ['MLG', 'MLSG'],
    'microsoft_traffic': ['Bing', 'Yahoo'],
    'listings_campaign': 'MLLIST'
}

# Product Classification Keywords
PRODUCT_KEYWORDS = {
    'auto': ['auto', 'car', 'vehicle'],
    'homeowners': ['home', 'homeowners'],
    'renters': ['renters', 'renter', 'apartment'],
    'condo': ['condo', 'condominium']
}


# ============================================================================
# ADS ACCOUNT HEALTH - HELPER FUNCTIONS
# ============================================================================

# Melon Max device codes (for UTM extraction)
_MELON_MAX_DEVICE_CODES = {"AM", "AT", "AD", "HM", "HT", "HD"}
