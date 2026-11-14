# BTC dip-bounce bot

A long-only trading bot for the make.fun BTC race. It trades one asset,
Coinbase Wrapped BTC against USDC, on one-minute bars.

How it works, in plain language: the bot listens for the hello message,
which carries the universe, the starting capital, the caps and the fees.
Then, for each batch, it reads the bar that just closed, the fills from
its previous orders, and its account. It keeps the recent closes and
looks for a sharp washout fall from a recent high, followed by evidence
that the fall is snapping back. When it sees that pattern it sends one
buy order for most of its cash. While it holds a position it watches
each new bar and sends one sell order when the price reaches a tight
take-profit, falls to a stop-loss, or gives back enough of its rise to
trip a trailing stop. It pauses new entries after its equity has fallen
too far from its peak, and it caps how many round trips it attempts, so
fees do not eat the edge. It sends exactly one reply, echoing the batch
sequence number, for every batch, and it stops quietly when the done
message arrives.

The bot uses only the Python standard library. It makes no network
calls, reads no wall clock and no environment, and uses no randomness,
so two runs on the same bars send the same orders.
