# Dive Twin: does a dreamed tank keep the real tank's shape?

## What it explores

Video models that make a film from one photograph are now pitched as world-makers: give them a picture, and they carry on into a place you can move through. A world has to keep its shape while you move through it, though, and "looks right" is not the same test as "is the same place".

Dive Twin puts one real place beside its dream, frame by frame. The place is a glass tank from the UW-TransStereo dataset, filmed with a ZED Mini stereo camera in five conditions: in air, in fresh water, in fresh water with the image enhanced, in salt water, and in salt water with pellets. Stereo gives the tank a measured shape. From one photograph of each condition, two engines (Runway Gen-4.5 and Wan 2.2) made 35 clips under three prompts: dive in, carry on as you like, and carry on with a nudge.

For every frame I estimate the dream's depth with a single-image model, fit it to the real tank once (one scale and one shift, on frame 0, never refitted), recover where the dream's camera went, and re-render the real tank from that spot. Two numbers come out per frame.

- **D** is how far the dream's tank is from the real one, as a multiple of a floor: how wrong the same depth model already is on the real footage. D = 1 is "no worse than measuring the real thing", and D = 3 is "the tank has changed shape".
- **V** is the share of the frame that can still be checked: pixels the rebuilt tank has seen, leaving out anything tracked as moving.

The page lets you scrub any clip and watch both at once: the real tank on the left, the dream's heat on the right, D as the scrubber's track, and a map of where the camera went.

## Why it matters

Three of the 35 clips leave the tank in a way the numbers can see. The clearest is the enhanced freshwater clip under Gen-4.5's nudged prompt. D passes 3 at frame 88 (3.7 s), 711 su along its path, and peaks at 5.37 at frame 105, while V stays at 1.00. Every pixel is still checkable, and the tank has turned into a ribbed hatch and a corridor that is not there. Two Wan clips in salt water leave too, at frames 97 and 102. Two more clips spike past 3 without holding it for half a second, 25 stay under 3 for their whole length, and in five the check runs out first: one path is lost, and four pellets clips pass the 100 su range the rebuilt tank can be trusted for.

Three things surprised me.

**V cannot see a dream leave; only D can.** The two Gen-4.5 clips whose far wall plainly opens into new space keep V at 1.00 from the first frame to the last, because the rebuilt tank still covers the frame. A coverage number alone would have passed them.

**The dreams open the tank up rather than fill it.** In the clips that flare, the invented space reads farther than the real tank: a corridor, a duct, a staircase room, a yard under open sky. The models extend the place outward more readily than they crowd it with things.

**A tracked actor still costs the tank.** When Wan fills the salt-water tank with people, I outline them and leave them out of D, yet D still climbs to 4.36 (frame 103) on the tank behind them, on a camera path that the tracks confirm is real. Outlining what moves does not fully isolate what it changes.

## What it suggests

A benchmark for world-making video should report shape against a measured place, frame by frame, with its floor stated beside it, and it should say where it can no longer check. "Unverifiable" is a result, not a zero; this page never prints it as one.

The method also travels. Any scene with a measured shape (a stereo pair, a scan, a survey) can be the real side. The dream needs nothing but its own frames.

## Limits

The real side is a reconstruction from stereo, not a recording, so it can only be re-seen from where a real camera looked; elsewhere it is grey. Its depth is in uncorrected stereo units (su), never millimetres: the stereo depth is not corrected for the tank's flat window. The camera path is anchored to the tank's own surfaces, so once a dream passes the far wall the path cannot follow it out. The first frame where D stays above 3 for half a second marks the departure instead. Each clip is one take per engine, prompt and recording: a sample, not a trait of the engine. The depth model's floor varies by condition, and on the real footage itself D sits between 0.68 and 1.33 (the median per recording), so D near 1 means "within the noise", not "perfect".

All the figures here come from the page's own `clips.json`. Data, CC BY 4.0: Smiles, A., Farkhatdinov, I., & Oh, C. (2025). UW-TransStereo: Underwater Stereo Vision Dataset for Transparent Object Detection & Ranging [Dataset]. Zenodo. RiTA 2025, King's College London. https://doi.org/10.5281/zenodo.16753748. The derived depth pictures are CC BY-NC-SA 4.0 (Stereo Anywhere, Depth Anything V2); the generated clips (Runway Gen-4.5, Wan 2.2) are the engines' output and are not under either licence.
