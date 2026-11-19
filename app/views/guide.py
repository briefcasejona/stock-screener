"""How to use it: the playbook's process in short, mapped to the pages."""
import streamlit as st

import core

PLAYBOOK = 'https://claude.ai/artifact/6wRvyX7Y5kfZuUweBT6r6x'


def render():
    st.title('How to use it')
    st.caption(core.DISCLAIMER)
    st.markdown(f"""
**Not sure what to do next?** The *Start here* page always shows your next step, with one button.

The full method is in your **Stock-Picking Playbook** ([open it]({PLAYBOOK})). This is the short version, page by page.

**Each month, by default, your €1,000 goes into the global index fund.** A single company gets money only when
everything below says yes, with at most 10% of your portfolio in one company.

1. **Screener: find ideas.** Start with the companies passing all 10 checks. Six ask whether it is a great business
   (high and steady return on capital, profits that turn into cash, little debt, margins that hold, no dilution);
   four ask whether it grows at a reasonable price. Passing means "worth a closer look", nothing more.
2. **Analyse.** Pick a company and press *Analyse and follow* (or *One-time analysis*). You get the growth today's
   price assumes (reverse DCF), a bear / base / bull value and up to ten years of history. You first write down your
   own estimate; then the program shows its value range, from a cautious starting rule for growth.
3. **Read the annual report.** What does the company sell, why do customers stay, what could go wrong?
   Then set your own growth rates on the *Your growth rates* tab and tick the box. Compare: does the price assume more
   growth than you believe?
4. **Decide with a margin of safety.** Buy-below is your base value minus the margin you pick on the Candidates page
   (20% unless you choose otherwise). The program shows only the fact: the price is above or at/below buy-below. The
   decision (Buy, Wait, No) is yours, written in the journal.
5. **Write it down.** Add a journal entry: why, and what would change your mind. Reading these back in a year teaches
   you more than any book.
6. **Follow.** The monthly check refreshes the companies you follow, re-runs the analysis when a new annual report is
   out, and notes price moves across your buy-below price. Do a full refresh every few months.

**Want to add a company the free sources miss** (many German and Swiss ones)? Download its annual report from the
company's investor-relations site and use *Add a report*. The ESEF version (a .zip, or an .xhtml file) is read
exactly; a PDF needs you to point out a few lines, which is a good way to learn to read the statements.
""")
    st.subheader('Words you will see')
    st.caption('Each word has one meaning, the same on every page. Many column names and figures have a ⓘ or a '
               'question mark: hover over it, or tap it, for the same explanation.')
    import glossary as G
    q = st.text_input('Look up a word', placeholder='For example: ROIC', key='glossary_q').strip().lower()
    hits = {w: t for w, t in G.WORDS.items() if not q or q in w.lower() or q in t.lower()}
    if not hits:
        st.caption('Not in the list. The Stock-Picking Playbook explains more.')
    st.markdown('\n'.join(f'- **{w}:** {t}' for w, t in sorted(hits.items(), key=lambda x: x[0].lower())))
