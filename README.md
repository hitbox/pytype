# PyType

A ZType inspired word typing game.

## ZType
https://zty.pe/

## words.txt
https://gist.github.com/deekayen/4148741

## Status

This code is a mess of me trying things out.

## NOTES from playing ZType

* Letters disappear immediately.

## TODO

* [ ] animate all movements (ex: turning the player ship).
* [ ] score system (hits/misses ratio).
* [ ] sounds

## CHANGELOG

### 2019-10-30 11:33:49

* Very basics working. Need end game conditions.

### 2019-10-31 08:11:31

* Changed to state stack and they work.
* Added update stack for gameplay to provide an intro.
* Added win/lose state.
* Debugging supports drawing now.
* Only Word sprites inside the space can be locked.

### 2019-11-01 15:11:51

* git init and put up on github.
* wait for explosions and animations to finish before changing state.
* fix bullets aren't disappearing after colliding.
* fire bullets at the letters.
* separate enemy text and ship so the ship can be rotated independently.
* display a ship that points at the letters.
