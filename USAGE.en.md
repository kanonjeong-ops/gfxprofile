# How to Use eGPU Game Config Swap

This plugin lets you save one set of settings per game for use with an eGPU and another for use with integrated graphics, then switch them all at once when needed. These are called the “eGPU” and “Internal” profiles.

When you save a profile, the current contents of the game’s graphics settings file are stored. When you apply a profile, the game’s settings file is replaced with the saved contents.

## First Time Only: Register Games

1. Open the plugin panel from Steam’s Quick Access Menu and go to “Detect games”.
2. Games with an Auto-selection candidate can be registered all at once. If a game has multiple candidates, you must pick the right one yourself.
3. If the game you want is not listed, run it once, open its graphics settings, close it completely, and use “Scan again”. If it still does not appear, use “Pick a file…”

Registering a game does not create its eGPU or Internal profile yet.

Only Proton games can be registered. Native Linux games keep their settings files outside the Proton prefix, so they cannot currently be registered.

## Save the eGPU Profile

1. With the eGPU connected, run a game you registered.
2. Set the graphics options for the eGPU as desired, then close the game completely.
3. From the plugin home screen, open “Apply / save per game”, then press “Save eGPU profile” on that game’s detail screen.

Saving while the game is running captures the values currently on disk. In games that rewrite their settings on exit, these may differ from the values you just selected.

If an eGPU profile already exists, a confirmation dialog appears before it is overwritten.

## Save the Internal Profile

With the eGPU disconnected, repeat the same steps and press “Save Internal profile”. Register any other games and save both profiles for them as well.

## Switch Profiles

1. Completely close the games you want to apply the profile to.
2. If the eGPU is connected, press “Apply eGPU profile” on the home screen. If you are using integrated graphics only, press “Apply Internal profile”.

The number beside each button is the number of games with that profile saved. Games without that profile are not included. Games already using the same settings are not changed.

To switch just one game, apply the profile directly from its row under “Apply / save per game”, or use an Apply button on its detail screen.

If a game’s current settings differ from every saved profile, a confirmation dialog appears before the profile is applied.

## Restore After Something Goes Wrong

Open “Restore a backup” from the game’s detail screen. The contents from immediately before an apply or save are backed up automatically. Up to 10 backups are kept per game; when that limit is exceeded, the oldest are removed first.

First check “Goes back into:” on each backup row. A profile backup goes back into that profile; any other backup goes back into the game’s settings file.

## Clean Up Registrations

“Unregister this game” on a game’s detail screen removes only the plugin’s registration and saved profiles. It does not touch the game’s own settings file. The unregistered game is also excluded from automatic detection.

You can change profile display names under “Settings”.

“Full reset” deletes all registrations, saved profiles, the detection-exclusion list, and display names you set.
