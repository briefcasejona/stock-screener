"""The six lessons of the research course. Each lesson: what to find, where to find it, why GARP cares, what the
classics teach. The classics are summarised in our own words with the source named, so you can read the original.

Free originals:
- Buffett's letters: https://www.berkshirehathaway.com/letters/letters.html
- Damodaran's lectures, notes and data: https://pages.stern.nyu.edu/~adamodar/
- Lynch (One Up on Wall Street, Beating the Street) and Fisher (Common Stocks and Uncommon Profits) are books; most
  libraries have them.
"""

BUFFETT = 'https://www.berkshirehathaway.com/letters/letters.html'
DAMODARAN = 'https://pages.stern.nyu.edu/~adamodar/'
EDGAR = 'https://www.sec.gov/edgar/search/'
XBRL = 'https://filings.xbrl.org/'
SPIVA = 'https://www.spglobal.com/spdji/en/research-insights/spiva/'

BEFORE = f"""
**Before lesson 1: two write-ups as your "before".** Do two write-ups now, with what you know today, on two companies
from your candidates. Each needs your own estimate, at least one claim and three figures checked in the annual report.
They are not graded. Later they show what the course changed: without a "before", any progress could just be practice.

**A fact to keep in mind all course long:** most professional fund managers fail to beat their index over 10 years or
more, after costs. S&P publishes this twice a year as the SPIVA scorecards ([SPIVA]({SPIVA})). Buffett himself told the
trustee of his wife's inheritance to put 90% in a low-cost S&P 500 index fund (2013 letter). That is why your monthly
money goes to the index fund by default, and why a pick has to earn its place.
"""

LESSONS = [
    {
        'title': 'Find it',
        'find': """
- The company's latest **annual report**. In the US that is the **10-K**; in Europe the annual report, often also as an
  **ESEF** file (a machine-readable version).
- Three figures in it, from the last full year: **revenue**, **operating income**, and **cash from operations**.
- The **number of shares** at year end, and how many there were a year earlier.
""",
        'where': f"""
- **The company's own website:** look for "Investors" or "Investor relations", then "Annual reports" or "Results".
- **US companies:** SEC EDGAR full-text search, [{EDGAR}]({EDGAR}). Type the company name, filter on form "10-K".
- **European companies:** [filings.xbrl.org]({XBRL}) lists ESEF annual reports by country and company. If a company
  is missing there (often German and Swiss ones), download the report from its website and use **Add a report** in this
  program.
- In a 10-K: revenue and operating income are in "Item 8. Financial Statements"; cash from operations is in the
  cash flow statement right after. The share count is on the cover page.
""",
        'why': """
Everything in GARP starts from the company's own filed numbers. Websites that copy them make mistakes, mix up years
and currencies, and mix "adjusted" numbers with real ones. If you can find the source yourself, you can check
anything the program or anyone else tells you.
""",
        'classics': f"""
- **Peter Lynch, One Up on Wall Street** (chapter "Getting the Facts"): the annual report is free, and the numbers
  that matter take a few minutes to find once you know where to look. Ask the investor-relations department when
  something is unclear: they answer questions.
- **Warren Buffett, 2002 letter** ([free]({BUFFETT})): footnotes you can't understand usually point to management
  you shouldn't trust. If they can't explain it plainly, they may not want to.
- **Philip Fisher, Common Stocks and Uncommon Profits** (chapter "What 'Scuttlebutt' Can Do"): the reports are the
  start, not the end. Fisher also talked to customers, suppliers and competitors. For you: read what customers and
  competitors say, too.
""",
        'do': 'Pick a company from your candidates, find its latest annual report, and write down the three figures and '
              'the share count. Compare them with the program\'s History tab. Then record the write-up below.',
    },
    {
        'title': 'Income statement',
        'find': """
- **Revenue** for the last 5 years: is it growing, and how fast?
- **Gross margin** (revenue minus cost of sales, as a share of revenue) and **operating margin** (operating income as
  a share of revenue). Are they steady, rising or falling?
- **Where the money comes from:** the segment note splits revenue by product line and by region.
- Anything called "one-off", "restructuring", "special items" or "adjusted".
""",
        'where': """
- The **income statement** in the financial statements (10-K Item 8, or the "consolidated statement of profit or
  loss" in a European report).
- The **segment note** ("Segment information"), usually one of the first notes after the statements.
- **Management's discussion** (10-K Item 7, "MD&A"; in Europe the "management report" or "financial review"): why
  revenue and margins moved.
""",
        'why': """
GARP buys growth. Revenue growth that comes with steady or rising margins means customers want more and the company
keeps its pricing power. Growth with falling margins is often bought: with discounts, or with acquisitions.
""",
        'classics': f"""
- **Lynch, One Up on Wall Street** (chapter "I've Got It, I've Got It: What Is It?"): sort a company first: slow grower,
  stalwart, fast grower, cyclical, turnaround or asset play. Each type is judged differently. A cyclical with a
  record year is not a fast grower.
- **Lynch** (chapter "Some Famous Numbers"): compare the P/E with the growth rate; a P/E around the growth rate is
  fair, well below it can be a bargain, well above it is expensive. This is the root of the PEG idea. Use it as a quick
  check, not a valuation.
- **Fisher, Common Stocks and Uncommon Profits** (chapter "What to Buy: The Fifteen Points"): his first points ask
  whether the products have a market that can grow sales for years, and whether management keeps developing new ones.
  His point on profit margins: a company needs good margins, and a plan to keep them.
""",
        'do': 'For one company, write down 5 years of revenue and operating margin, and one sentence on where growth came '
              'from. Then record the write-up below.',
    },
    {
        'title': 'Balance sheet and cash flow',
        'find': """
- **Debt:** total borrowings, minus cash. Compare it with a year's operating income: more than 3 years' worth is a
  warning sign for most companies.
- **Cash from operations** vs **net income**, for 5 years. Over time they should be close.
- **Free cash flow:** cash from operations minus capital expenditure (spending on buildings and machines).
- **Share count** over 5 years: falling (buybacks) or rising (new shares, often paid to staff)?
""",
        'where': """
- The **balance sheet** ("statement of financial position") for cash and borrowings; the **debt note** for when it
  must be repaid and at what interest.
- The **cash flow statement**: cash from operations at the top, capital expenditure ("purchases of property, plant and
  equipment") in the investing part, buybacks and dividends in the financing part.
""",
        'why': """
Profit is an opinion; cash is a fact. A company whose profit doesn't turn into cash may be booking sales too early or
needing ever more stock and machines. Debt decides whether a bad year is an annoyance or a disaster. The program values
companies on free cash flow per share for exactly this reason.
""",
        'classics': f"""
- **Buffett, 1986 letter** ([free]({BUFFETT})): "owner earnings": roughly, profit plus depreciation, minus the
  spending the business needs just to stay where it is. That is what an owner can actually take out. Free cash flow
  is a practical version of the same idea.
- **Lynch, One Up on Wall Street** (chapter "Some Famous Numbers"): look at cash and debt on the balance sheet, and at
  inventories growing faster than sales, a warning sign.
- **Damodaran** ([free]({DAMODARAN})): growth is not free. A company grows by reinvesting, and how much growth a euro
  of reinvestment buys depends on its return on capital. Growth with a low return on capital can destroy value.
""",
        'do': 'For one company, compare 5 years of cash from operations with net income, and write down its debt and '
              'share count trend. Then record the write-up below.',
    },
    {
        'title': 'Moat and management',
        'find': """
- **Why customers stay:** what would it cost them to switch? Is there a brand, a network, a patent, a cost advantage,
  or a product built into their work?
- **Return on capital** over 5-10 years: a company that keeps earning well above ~10% probably has a moat.
- **How management spends spare cash:** dividends, buybacks (at what prices?), acquisitions (did they work?), debt.
- **Pay:** what the bosses are paid for. Rewards for size or "adjusted" profit are weaker than for return on capital
  or per-share results.
""",
        'where': """
- **Business description** (10-K Item 1; the "strategy" or "business model" part of a European report): customers,
  competitors, how they sell.
- **Cash flow statement**, financing part: buybacks and dividends. The note on **share-based payments**: new shares
  given to staff.
- **Remuneration report** (Europe) or the **proxy statement** "DEF 14A" (US, on EDGAR): what the bosses are paid for.
- The **CEO's letter** in the annual report, compared with the same letter from 3 years ago: did they do what they
  said?
""",
        'why': """
GARP pays for growth years ahead. That only works if competitors can't take the profits away (the moat) and if
management doesn't waste the cash the business makes.
""",
        'classics': f"""
- **Buffett, 2007 letter** ([free]({BUFFETT})): a great business has a lasting competitive advantage (a "moat"), and
  needs little extra capital to grow. He contrasts "great", "good" and "gruesome" businesses.
- **Buffett, 1989 letter**: "It's far better to buy a wonderful company at a fair price than a fair company at a
  wonderful price." The same letter warns about the "institutional imperative": managers copying each other and
  spending cash on deals because they can.
- **Buffett, Owner's Manual** (in every annual report since the 1980s): each dollar a company keeps should, over
  time, create at least a dollar of market value.
- **Fisher, Common Stocks and Uncommon Profits** ("The Fifteen Points"): does management talk openly with shareholders
  when things go wrong, or only when things go well? And is its integrity beyond doubt? Fisher called a "no" on
  integrity a reason to walk away whatever the numbers say.
""",
        'do': 'For one company, write down why customers stay in one sentence, its return on capital trend, and what '
              'management did with spare cash in the last 5 years. Then record the write-up below.',
    },
    {
        'title': 'Risks and red flags',
        'find': """
- The **3 risks** from the report's risk section that would hurt most, in your own words.
- **"One-off" costs that come back** every year.
- **Profit rising while cash flow doesn't**, or customers taking longer to pay (receivables growing faster than sales).
- **Changes of auditor** or of accounting rules, and anything in the audit report beyond the standard text.
- **Your own biases:** what do you want to be true about this company?
""",
        'where': """
- **Risk factors** (10-K Item 1A; "principal risks" in a European report).
- The **auditor's report**: "key audit matters" tell you what the auditor worried about.
- Notes on **revenue recognition**, **receivables** and **provisions**.
""",
        'why': """
GARP's margin of safety only protects you from risks you have priced in. A beginner's biggest losses come from what
they didn't read, or chose not to see.
""",
        'classics': f"""
- **Buffett, 2002 letter** ([free]({BUFFETT})): beware weak accounting (if a company plays games with how it reports,
  the games probably don't stop there), footnotes you can't understand, and companies that trumpet earnings forecasts.
- **Lynch, One Up on Wall Street** (chapter "Stocks I'd Avoid"): the hottest stock in the hottest industry,
  "diworsification" (buying businesses unrelated to the core), and companies that depend on one customer.
- **Fisher, Common Stocks and Uncommon Profits** ("Five Don'ts for Investors"): don't buy a stock because you like
  the tone of its annual report; a polished report can hide a weak business. ("Five More Don'ts"): don't follow the
  crowd.
- **Your biases** (a box, not a lesson): *confirmation bias*: searching only for what supports your view. *Anchoring*:
  sticking to the first price you saw. *Overconfidence*: your 80%-sure claims will show whether you are. A simple fix
  from both Lynch and Buffett: write down why you would be wrong before you decide.
""",
        'do': 'For one company, write down the 3 biggest risks, one red-flag check you did and what it showed, and what '
              'would make you change your mind. Then record the write-up below.',
    },
    {
        'title': 'Value and decide',
        'find': """
- **Your own growth rate** for free cash flow per share, and what one share is worth to you, **before** you look at
  the program's numbers (the Candidates page asks for this first).
- The program's **reverse DCF**: the growth the price assumes. Is that more or less than you expect?
- **Your decision:** Buy (on paper, during the course), Wait, or No. And **when you would sell**.
- **Dated claims** that can turn out wrong, with how sure you are.
""",
        'where': """
- **Candidates** page: your estimate first, then the valuation, the 10 checks, the history and your own growth rates.
- **Journal**: your decision with "what would change my mind", and your claims.
- **Scoreboard**: a paper buy, with a one-line reason.
""",
        'why': """
GARP means a good, growing company at a reasonable price. A wonderful company bought at a price that already assumes
everything goes right is a bad investment. The reverse DCF turns the price into a growth rate you can judge; your
margin of safety is your room for being wrong.
""",
        'classics': f"""
- **Buffett, 1992 letter** ([free]({BUFFETT})): "growth" and "value" are not opposites. A company is worth the cash it
  will produce, discounted to today; growth is part of that sum, and it only adds value when the company earns more on
  new money than the money costs.
- **Buffett, 1987 letter**: "Mr. Market" offers you a price every day, sometimes silly, sometimes sad. You can use his
  moods; you must never let them guide you.
- **Damodaran** ([free]({DAMODARAN})): every valuation is a story and numbers. If you can't tell the story behind your
  growth rate in a few sentences, the number is a guess. And every valuation is wrong; the question is by how much.
- **Lynch, One Up on Wall Street** (chapter "The Two-Minute Drill"): before buying, say in two minutes why you are
  interested, what has to happen for the company to do well, and what could go wrong.
- **Fisher, Common Stocks and Uncommon Profits** (chapter "When to Sell and When Not To"): sell when you made a mistake
  about the company, when it no longer passes your tests, or when you find something clearly better. Not because the
  price went up.
""",
        'do': 'For one company, do the full routine: your estimate, the program\'s numbers, a decision with when you '
              'would sell, and at least two claims. Then record the write-up below.',
    },
]

PASS_FAIL = ('After 24 months, the course worked if my claims came true more often than the simple forecast and my '
             'confidence levels were roughly right (my 80%-sure claims came true about 80% of the time). It failed if my '
             'claims were no better than the simple forecast.')
