"""How to use it: the playbook's process in short, mapped to the pages."""
import streamlit as st

import core

PLAYBOOK = 'https://claude.ai/artifact/6wRvyX7Y5kfZuUweBT6r6x'


def render():
    st.title('How to use it')
    st.caption(core.DISCLAIMER)
    st.markdown(f"""
The full method is in your **Stock-Picking Playbook** ([open it]({PLAYBOOK})). This is the short version, page by page.

**Each month, by default, your €1,000 goes into the global index fund.** A single company gets money only when
everything below says yes, with at most 10% of your portfolio in one company.

1. **Screener: find ideas.** Start with the companies passing all 10 checks. Six ask whether it is a great business
   (high and steady return on capital, profits that turn into cash, little debt, margins that hold, no dilution);
   four ask whether it grows at a reasonable price. Passing means "worth a closer look", nothing more.
2. **Analyse.** Pick a company and press *Analyse and follow* (or *One-time analysis*). You get the growth today's
   price assumes (reverse DCF), a bear / base / bull value and ten years of history. The growth rates come from a
   cautious starting rule, so the decision can read *Deep dive* but never *Buy* yet.
3. **Deep dive: read the annual report.** What does the company sell, why do customers stay, what could go wrong?
   Then set your own growth rates on the *Your growth rates* tab and tick the box. Compare: does the price assume more
   growth than you believe?
4. **Decide with a margin of safety.** Buy-below is your base value minus the margin you pick on the left (30% unless
   you choose otherwise). Above it: wait. At or below it, with reviewed growth rates: the playbook says buy.
5. **Write it down.** Add a journal entry: why, and what would change your mind. Reading these back in a year teaches
   you more than any book.
6. **Follow.** The weekly check refreshes the companies you follow, re-runs the analysis when a new annual report is
   out, and notes price moves across your buy-below price. Do a full refresh every few months.

**Want to add a company the free sources miss** (many German and Swiss ones)? Download its annual report from the
company's investor-relations site and use *Add a report*. The ESEF version (a .zip, or an .xhtml file) is read
exactly; a PDF needs you to point out a few lines, which is a good way to learn to read the statements.
""")
    st.subheader('Words you will see')
    st.markdown("""
- **Free cash flow (FCF):** cash from operations minus investment in equipment and software. What the owners could
  take out each year.
- **DCF:** the value of a share as all its future cash flows, discounted back to today. *Reverse DCF* turns it around:
  which growth makes the value equal to today's price?
- **Discount rate:** the yearly return you ask for. Higher means a lower value today.
- **ROIC:** return on invested capital. Above 15% for years usually means a moat: something competitors cannot copy.
- **Margin of safety:** buying well below your estimate of value, because the estimate can be wrong.
- **Normalised cash flow:** for cyclical companies, the average margin times today's revenue, so one boom or bust
  year does not drive the value.
""")
