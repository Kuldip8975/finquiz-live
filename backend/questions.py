"""The quiz questions. They live only on the server.

`correct` is the index (0-3) of the right option. It is never sent to a
player's phone until the question has closed (see game.py -> player_view).

To add a question, copy one block and edit it. Each needs exactly four options
and a source link for the fact behind it.
"""

QUESTIONS = [
    {
        "text": "Using the Rule of 72, about how many years does money take to double at 8% interest a year?",
        "options": ["About 6 years", "About 9 years", "About 12 years", "About 18 years"],
        "correct": 1,
        "explanation": "72 ÷ 8 = 9 years.",
        "source": "https://www.investor.gov/introduction-investing/investing-basics/glossary/rule-72",
    },
    {
        "text": "You deposit ₹10,000 at 10% a year, compounded yearly. How much do you have after 2 years?",
        "options": ["₹11,000", "₹12,000", "₹12,100", "₹12,500"],
        "correct": 2,
        "explanation": "Year 1: ₹11,000. Year 2 earns interest on ₹11,000 too: ₹12,100.",
        "source": "https://www.investor.gov/introduction-investing/investing-basics/glossary/compounding-interest",
    },
    {
        "text": "If an Indian bank fails, DICGC deposit insurance covers up to how much per depositor, per bank?",
        "options": ["₹1 lakh", "₹2 lakh", "No limit", "₹5 lakh"],
        "correct": 3,
        "explanation": "Raised from ₹1 lakh to ₹5 lakh in February 2020, principal and interest together.",
        "source": "https://website.rbi.org.in/en/web/rbi/-/press-releases/deposit-insurance-and-credit-guarantee-corporation-dicgc-increases-the-insurance-coverage-for-depositors-in-all-insured-banks-to-%E2%82%B9-5-lakh-49330",
    },
    {
        "text": "A CIBIL credit score in India is a number in which range?",
        "options": ["300 to 900", "0 to 100", "1 to 10", "100 to 1,000"],
        "correct": 0,
        "explanation": "The closer to 900, the better lenders view your application.",
        "source": "https://www.cibil.com/blog/what-is-cibil-score",
    },
    {
        "text": "A Public Provident Fund (PPF) account matures after how many years?",
        "options": ["5 years", "10 years", "15 years", "20 years"],
        "correct": 2,
        "explanation": "PPF matures after 15 years and can be extended in blocks of 5 years.",
        "source": "https://en.vikaspedia.in/social-welfare/financial-inclusion/financial-literacy/long-term-savings-and-investments/public-provident-fund-(ppf)",
    },
]


def _check(questions):
    for i, q in enumerate(questions):
        assert len(q["options"]) == 4, f"Question {i + 1} needs 4 options"
        assert 0 <= q["correct"] < 4, f"Question {i + 1} has a bad 'correct' index"
        assert q["source"].startswith("https://"), f"Question {i + 1} needs a source link"


_check(QUESTIONS)
