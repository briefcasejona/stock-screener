"""The words the program uses, each with one meaning. The guide page lists them all; pages use them as help on a
column or a figure (glossary.say('ROIC')), so a word means the same everywhere."""

WORDS = {
    'Annual report': 'The yearly report a listed company must publish, with its audited figures and what management '
                     'says about the year. The source for everything else here.',
    'Bear / base / bull': 'Three values for one share: from cautious growth (bear), the growth you expect (base) and '
                          'hopeful growth (bull). The truth is usually somewhere in the range, not on one number.',
    'Box 3': 'The Dutch tax on savings and investments: a yearly tax on what you own on 1 January. There is no tax on '
             'a gain when you sell.',
    'Buy-below price': 'Your base value minus your margin of safety. The price being below it is a fact, not advice: '
                       'whether to buy is your decision.',
    'Cash/share growth': 'How fast free cash flow per share grew a year over the years shown.',
    'Check (passed / failed)': '"Pass" is only ever used for one of the 10 checks: a company passes or fails a check. '
                               'Your own decision is Buy, Wait or No.',
    'Claim': 'A prediction you write down about a company\'s figures in a year that has not ended ("revenue grows '
             'more than 8% a year to 2027"), with how sure you are. The program checks it when the figures are out.',
    'Closer look': 'What passing all 10 checks means: the company is worth reading about. Never "buy".',
    'DCF (discounted cash flow)': 'The value of a share as all its future free cash flows, each counted for less the '
                                  'further away it is (discounted). Small changes in growth move it a lot.',
    'Discount rate': 'The yearly return you ask for. The program uses 9% for every company. Higher means a lower value '
                     'today.',
    'Dilution': 'New shares issued, so each existing share owns a smaller part of the company.',
    'Free cash flow (FCF)': 'Cash from running the business minus what it spends on buildings, machines and software. '
                            'What the owners could take out each year.',
    'GARP': 'Growth at a reasonable price: 4 of the 10 checks ask whether the growth is real and the price not too '
            'high for it.',
    'Gross margin': 'What is left of each euro of sales after the direct cost of making what was sold.',
    'Index fund': 'A fund that owns all the companies in an index, like the whole world\'s shares. The default for '
                  'every month\'s money; a pick has to do better than it.',
    'Margin of safety': 'Buying well below your estimate of value, because the estimate can be wrong. 10%, 20% or 30% '
                        'here; 20% unless you choose otherwise.',
    'Moat': 'Something that keeps competitors away for years: a brand, a network, costs nobody else can match, '
            'customers who can\'t easily switch.',
    'No': 'Your decision not to buy a company. (It used to be called "Pass", which now only means a passed check.)',
    'Normalised cash flow': 'For a company whose profits rise and fall with the economy: the average cash-flow margin '
                            'times today\'s revenue, so one boom or bust year does not drive the value.',
    'P/E (price / earnings)': 'The price of a share divided by one year\'s profit per share. 20 means you pay 20 years '
                              'of today\'s profit.',
    'Paper trade': 'A practice trade on the Scoreboard: no real money, at the latest price, dated today.',
    'Quality': '6 of the 10 checks: is it a great business? High and steady ROIC, profits that turn into cash, little '
               'debt, margins that hold, no dilution.',
    'Reverse DCF / growth the price assumes': 'The DCF turned around: which yearly growth makes the value equal to '
                                              'today\'s price? Compare it with the growth you believe.',
    'ROIC': 'Return on invested capital: profit on the money put into the business. Well above 10-15% for years '
            'usually means a moat. "Median": the middle year of those shown.',
    'Still researching': 'Your decision when you haven\'t decided yet. (It used to be called "Deep dive".)',
    'Wait': 'Your decision that the company is good but the price is too high: you follow it until it is lower.',
}


def say(word):
    """The meaning of a word, for a help text."""
    return WORDS[word]
