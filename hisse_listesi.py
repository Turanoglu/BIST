"""
BIST Hisse Listesi
TradingView'de turkey market formatı: BIST:THYAO
"""

BIST30 = [
    "AKBNK","ARCLK","ASELS","BIMAS","DOHOL","EKGYO","EREGL",
    "FROTO","GARAN","HEKTS","ISCTR","KCHOL","KOZAA","KOZAL",
    "KRDMD","MGROS","PETKM","PGSUS","SAHOL","SASA","SISE",
    "SKBNK","TAVHL","TCELL","THYAO","TKFEN","TOASO","TTKOM",
    "TUPRS","VAKBN",
]

BIST100 = BIST30 + [
    "AEFES","AGESA","AGHOL","AKGRT","AKSA","AKSEN","ALARK",
    "ALBRK","ALFAS","ALGYO","ALKIM","ANACM","ASUZU","AYDEM",
    "AYEN","BAGFS","BANVT","BFREN","BIZIM","BNTAS","BRISA",
    "BRYAT","BSOKE","BTCIM","CCOLA","CEMAS","CIMSA","CLEBI",
    "CWENE","DOAS","DOBUR","DOGUB","EGEEN","ENKA","ERBOS",
    "EUPWR","FENER","FLAP","GLYHO","GMTAS","GOODY","GOZDE",
    "GRSEL","GSDHO","GSRAY","GUBRF","GWIND","HATEK","HLGYO",
    "HRKET","ICBCT","INDES","INFO","ISGYO","ISDMR","ISFIN",
    "ISGSY","KAREL","KERVT","KLNMA","KONYA","KORDS","LOGO",
    "MAVI","MPARK","NUHCM","ODAS","OKEY","OTKAR","OYAKC",
    "PINSU","POLYE","PRDGS","RYSAS","SELEC","SNGYO","SOKM",
    "TATGD","TSKB","TTRAK","ULKER","VESBE","VESTL","YKBNK",
    "YUNSA","ZRGYO",
]

BIST_DISI = [
    "ACSEL","ADEL","ADESE","AFYON","AKCNS","AKFGY","AKFIN",
    "AKMGY","AKNON","AKPAZ","AKSGY","AKSUE","AKYHO","ALCTL",
    "ALKLC","ALMAD","ALNTF","ALTINS","ALTNY","ALVES","ALYAG",
    "ARASE","ARHOL","ARMDA","ARSAN","ARTMS","ARZUM","ASTOR",
    "ATATP","ATEKS","AYES","AYGAZ","BASGZ","BAYRK","BERA",
    "BEYAZ","BIENY","BJKAS","BLCYT","BMSCH","BORSK","BOSSA",
    "BRKO","BRKVY","BRSAN","BSTOB","BUCIM","BURCE","BURVA",
    "BVSAN","CANTE","CAYGY","CEOEM","COFAZ","DAGI","DAPGM",
    "DARDL","DENGE","DESA","DEVA","DIRIT","DITAS","DMSAS",
    "DOCO","DOKTA","DUNIH","DYOBY","EBEBK","EDATA","EDIP",
    "EFOR","EGEPO","EKSUN","ELITE","EMKEL","EMNIS","EPLAS",
    "ERBU","ERCAN","ERCB","ESEN","ESGYO","EUKYO","EYGYO",
    "FADE","FIGEN","FONET","FORMT","GEDZA","GENIL","GENTS",
    "GEREL","GIPTA","GLBMD","GLRYH","GOKAK","GOLTS","GORBN",
    "GPRGD","GRNYO","GSDDE","GUNDG","HEDEF","HOROZ","HUBVC",
    "HUNER","HURGZ","IDGYO","IEYHO","IHEVA","IHGZT","IHLAS",
    "IHLGM","IHYAY","IKMAS","IKTLL","IMASM","INTEM","INVES",
    "IPEKE","ISATR","ISKUR","ISYAT","ITFIN","IYIBIL","JANTS",
    "JOYFT","KAPLM","KARSN","KARTN","KATMR","KERVN","KFEIN",
    "KGYO","KHGYO","KILER","KLGYO","KLKIM","KLMSN","KLRHO",
    "KLSER","KMPUR","KNFRT","KONTR","KOPOL","KRPLS","KSTUR",
    "KTLEV","KTSKR","KUTPO","LIDER","LIDFA","LILAK","LINK",
    "LKMNH","LRSHO","MAALT","MACKO","MAGEN","MAKIM","MANAS",
    "MARBL","MARKA","MARTI","MEDTR","MEGMT","MEPET","MERCN",
    "MERIT","MERKO","METRO","MIATK","MIELS","MMCAS","MNDRS",
    "MODAS","MOBTL","MRGYO","MRSHL","MTRKS","MTRYO","MUGLA",
    "MUTLU","NATEN","NETAS","NIBAS","NILYT","NKAS","NKHOL",
    "NUGYO","OFSYM","ORCAY","ORGE","ORMA","OSMEN","OSTIM",
    "OYAYO","PAMEL","PANTR","PAPIL","PCILT","PENTA","PETUN",
    "PKENT","PLTUR","PMTAS","POLHO","POLTK","PPKRT","PRATK",
    "PRZMA","PSGYO","PTOFS","PTSAS","RALYH","RAYSG","REEDR",
    "RGYAS","RHEAG","RNPOL","RODRG","ROTET","RUBNS","SAFKN",
    "SAMAT","SANFM","SANKO","SARKY","SAYAS","SDTTR","SEGYO",
    "SEKFK","SEKUR","SELGD","SELVA","SEYKM","SILVR","SNKRN",
    "SNPAM","SNPMS","SNTKS","SODSN","SOKE","SONME","SUMAS",
    "SUNBK","SUWEN","TEKTU","TEZOL","TGSAS","TKNSA","TLMAN",
    "TMPOL","TNZTP","TRCAS","TRGYO","TRILC","TRKHL","TRMKS",
    "TRPGM","TUMAS","TUKAS","TUCLK","TURGZ","TURSG","ULUSE",
    "ULUUN","UMPAS","UNLU","USAK","UZERB","VAKFN","VAKKO",
    "VANGD","VBTYZ","VERUS","VKFYO","VKGYO","VLBRK","VRGYO",
    "YAPRK","YAVAS","YATAS","YBTAS","YEOTK","YESIL","YGGYO",
    "YIGIT","YKSLN","ZEDUR","ZEREN","ZEVKM","ZNGYO","ZORLU",
]

BIST_ALL = list(dict.fromkeys(BIST100 + BIST_DISI))

SEKTOR_MAP = {
    "AKBNK":"Bankacılık","GARAN":"Bankacılık","HALKB":"Bankacılık",
    "ISCTR":"Bankacılık","SKBNK":"Bankacılık","VAKBN":"Bankacılık",
    "YKBNK":"Bankacılık","ALBRK":"Bankacılık","ICBCT":"Bankacılık",
    "TSKB":"Bankacılık","QNBFK":"Bankacılık",
    "AKSEN":"Enerji","AYEN":"Enerji","EUPWR":"Enerji","GWIND":"Enerji",
    "CWENE":"Enerji","ODAS":"Enerji","AYDEM":"Enerji","NATEN":"Enerji",
    "TUPRS":"Enerji","PETKM":"Enerji",
    "KOZAL":"Madencilik","KOZAA":"Madencilik",
    "THYAO":"Havacılık","PGSUS":"Havacılık","TAVHL":"Havacılık","CLEBI":"Havacılık",
    "ASELS":"Teknoloji","LOGO":"Teknoloji","NETAS":"Teknoloji","INDES":"Teknoloji",
    "ARMDA":"Teknoloji","KAREL":"Teknoloji","FONET":"Teknoloji","LINK":"Teknoloji",
    "BIMAS":"Perakende","MGROS":"Perakende","SOKM":"Perakende","MAVI":"Perakende",
    "DOAS":"Perakende","BIZIM":"Perakende","OKEY":"Perakende",
    "ULKER":"Gıda","TATGD":"Gıda","BANVT":"Gıda","AEFES":"Gıda",
    "CCOLA":"Gıda","PETUN":"Gıda","PINSU":"Gıda",
    "FROTO":"Otomotiv","TOASO":"Otomotiv","TTRAK":"Otomotiv","OTKAR":"Otomotiv",
    "ASUZU":"Otomotiv","BRISA":"Otomotiv",
    "KCHOL":"Holding","SAHOL":"Holding","DOHOL":"Holding","TKFEN":"Holding",
    "GLYHO":"Holding","AGHOL":"Holding",
    "EREGL":"Demir-Çelik","KRDMD":"Demir-Çelik","ISDMR":"Demir-Çelik",
    "EKGYO":"GYO","ALGYO":"GYO","HLGYO":"GYO","SNGYO":"GYO","ZRGYO":"GYO",
    "TCELL":"Telekomünikasyon","TTKOM":"Telekomünikasyon",
    "AKGRT":"Sigorta","AGESA":"Sigorta",
    "SASA":"Kimya","HEKTS":"Tekstil","BRSAN":"Metal","ENKA":"İnşaat",
}

def get_sektor(ticker: str) -> str:
    return SEKTOR_MAP.get(ticker, "Diğer")

def get_endeks(ticker: str) -> str:
    if ticker in BIST30:  return "BIST30"
    if ticker in BIST100: return "BIST100"
    return "BIST+"

def get_hisse_listesi(endeks: str) -> list:
    if endeks == "BIST30":      return list(BIST30)
    if endeks == "BIST100":     return list(BIST100)
    if endeks == "BIST100Disi": return list(BIST_DISI)
    return list(BIST_ALL)

# TradingView format: "BIST:THYAO"
def to_tv_format(tickers: list) -> list:
    return [f"BIST:{t}" for t in tickers]

def from_tv_format(tv_ticker: str) -> str:
    return tv_ticker.replace("BIST:", "").split(":")[0]
