# Synchronous FIFO

The FIFO holds four 8-bit words and has active-low reset. A write is accepted when requested and the FIFO is not full. A read is accepted when requested and the FIFO is not empty. The read data is the current head before the accepting clock edge.

- FIFO-RESET. Reset clears occupancy and asserts empty.
- FIFO-ORDER. Accepted reads return all accepted words in insertion order.
- FIFO-BOUNDS. Occupancy remains in the inclusive range zero to four.
- FIFO-SIMULTANEOUS. When a read and a write are accepted on the same clock edge, occupancy is unchanged.
- FIFO-REACH. Simultaneous accepted reads and writes are reachable from reset.
