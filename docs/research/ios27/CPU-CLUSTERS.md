# SM8475 CPU clusters in our device tree

Date: 2026-11-21. Status: **open question, no change made.**

## What the tree says

The SoC feed (`UniXNU-sm8475-common`, pin `20a30fd`) declares eight CPUs in
`dts/sm8475.dtsi:22-59`, and every one of them carries the same label:

```
/* cpu@0: prime */        cpu@0 { reg = <0x000>; unixnu,cluster-type = "P"; };
/* cpu@1: performance */  cpu@1 { reg = <0x100>; unixnu,cluster-type = "P"; };
...
/* cpu@7: performance */  cpu@7 { reg = <0x700>; unixnu,cluster-type = "P"; };
```

Our own `dts/mondrian.dts` does not repeat them; it pulls the file in with
`/include/ "sm8475.dtsi"`, which is correct and is what the flash image shows:

```
$ dtc -I dtb -O dts .../device-tree/hardware.dtb | grep -c 'unixnu,cluster-type'
8
$ ... | grep -o 'unixnu,cluster-type = "[A-Z]"' | sort | uniq -c
      8 unixnu,cluster-type = "P"
```

## Why that is suspicious

SM8475 is a 1 + 3 + 4 part: one Cortex-X2, three Cortex-A710, four Cortex-A510.
Eight cores is right; **four of them being labelled performance is not**. The
comments repeat the word "performance" for `cpu@4` through `cpu@7`, which is the
signature of a file written out by hand from a 4 + 4 assumption rather than
generated from the part's real layout.

Nothing in our tree reads this property today: our stage-0 kernel publishes the
cores through `drivers/ArmCpu`, and the boot only has to reach `bsd_init`. So
this is not a flight blocker. It becomes one the moment anything partitions work
by cluster type — the scheduler's performance/efficiency split, or a thermal or
frequency policy keyed on the same label.

## What I deliberately did not do

I did not flip four labels to `"E"`. Two reasons:

1. The property's consumer is not in this repository, so the meaning of `"P"` and
   `"E"` here is assumed, not read. If the consumer expects a third value, or
   expects the label on a cluster node rather than per CPU, guessing would
   produce a tree that parses and lies.
2. The sub-file lives in the SoC feed. Changing it changes every board that
   consumes `sm8475.dtsi`, and it would need a feed pin bump to be reproducible.

## What would settle it

- Read the consumer: grep the framework and `UniXNU-sheng` for
  `unixnu,cluster-type` and for the DT property name the CPU provider actually
  parses. Record `file:line` for each reader.
- Compare with a board whose core layout is not in doubt: sheng is SM8550
  (1 + 4 + 3) and its `dts/` should show at least one `"E"` if the label means
  what it looks like.
- Only then change the labels, in the feed, with the pin bumped and a diff of
  the compiled `hardware.dtb` proving exactly which properties moved.

## Related

`P-287` records the reading error that produced this finding in the first place:
one audit reported "`dts/mondrian.dts` has zero `unixnu,cluster-type`" and called
it unmet, because it read the board file and not the include chain. The property
is present eight times; the count was never the issue. The label is.
