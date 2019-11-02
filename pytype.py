import abc
import argparse
import collections
import contextlib
import itertools as it
import math
import os
import random
import string

with contextlib.redirect_stdout(open(os.devnull,'w')):
    import pygame as pg

POPSTATE = pg.USEREVENT + 0
PUSHSTATE = pg.USEREVENT + 1

cooldowns = collections.defaultdict(int)
debugstack = []

def abs_angle_to(p1, p2):
    x1, y1 = p1
    x2, y2 = p2
    dx, dy = x2 - x1, y2 - y1
    return (math.tau + math.atan2(-dy, dx)) % math.tau

def debug(arg):
    debugstack.append(arg)

def haspunctuation(word):
    return any(letter in string.punctuation for letter in word)

def lerp(a, b, t):
    return a * (1 - t) + b * t

def lerpi(a, b, t):
    container = type(a)
    return container(lerp(c, d, t) for c, d in zip(a, b))

def popstate():
    pg.event.post(pg.event.Event(POPSTATE))

def pushstate(state):
    pg.event.post(pg.event.Event(PUSHSTATE, state=state))

def quit():
    pg.event.post(pg.event.Event(pg.QUIT))

def random_location(rect, inside, avoiding=None, limit=None):
    rect = rect.copy()
    if limit is None:
        limit = math.inf
    count = it.count()
    while next(count) < limit:
        rect.center = (random.randint(inside.left, inside.right),
                       random.randint(inside.top, inside.bottom))
        rect.clamp_ip(inside)
        if not avoiding:
            break
        else:
            for other in avoiding:
                if rect.colliderect(other):
                    # no good, it's colliding, break inner loop
                    break
            else:
                # not colliding any others, break outer loop
                break
    return rect

def rectat(rect, **kwargs):
    rect = rect.copy()
    for key, value in kwargs.items():
        setattr(rect, key, value)
    return rect

def wrap(rects):
    """
    Return bounding rect of rects.
    :param rects: iterable of pg Rects
    """
    lefts, tops, rights, bottoms = it.tee(rects, 4)
    left = min(rect.left for rect in lefts)
    top = min(rect.top for rect in tops)
    right = max(rect.right for rect in rights)
    bottom = max(rect.bottom for rect in bottoms)
    return pg.Rect(left, top, right - left, bottom - top)

class Clock:
    "Wrap pg Clock to remember what the framerate should be."

    def __init__(self, framerate):
        self.framerate = framerate
        self._clock = pg.time.Clock()
        self.get_fps = self._clock.get_fps

    def tick(self):
        return self._clock.tick(self.framerate)


class Screen:
    "Wrap the surface returned by pg.display.set_mode and add handy Rect and methods."

    def __init__(self, size):
        self.surf = pg.display.set_mode(size)
        self.rect = self.surf.get_rect()
        self.background = self.surf.copy()

    def clear(self):
        self.surf.blit(self.background,(0,0))

    def update(self):
        pg.display.flip()


class State:

    def enter(self):
        "The engine has just switched to this state"

    def exit(self):
        "The engine is leaving this state"

    @abc.abstractmethod
    def handle(self, event):
        "Handle event"

    @abc.abstractmethod
    def update(self, elapsed):
        "Update state"

    @abc.abstractmethod
    def draw(self, surf):
        "Draw state"


class StateManager:
    "Stack based state managing"

    def __init__(self, initial=None):
        if initial is None:
            initial = []
        self.stack = initial

    @property
    def current(self):
        if self.stack:
            return self.stack[-1]

    def pop(self):
        popped = self.stack.pop()
        if popped:
            popped.exit()
        if self.stack:
            self.stack[-1].enter()
        return popped

    def push(self, state):
        if self.stack:
            self.stack[-1].exit()
        self.stack.append(state)
        state.enter()

    def update(self):
        "Handle any state changing events"
        for event in pg.event.get():
            if event.type == POPSTATE:
                self.pop()
            elif event.type == PUSHSTATE:
                self.push(event.state)
            else:
                pg.event.post(event)


class Engine:
    "Handle switching states and properly executing the current state's methods."

    def __init__(self, clock, screen, state_manager, debug_renderer=None):
        self.clock = clock
        self.screen = screen
        self.state_manager = state_manager
        self.debug_renderer = debug_renderer

    def run(self):
        while not pg.event.peek(pg.QUIT):
            elapsed = self.clock.tick()
            self.state_manager.update()
            if not self.state_manager.current:
                break
            for event in pg.event.get():
                self.state_manager.current.handle(event)
            # update cooldowns
            for key, value in cooldowns.items():
                if value > 0:
                    cooldowns[key] -= elapsed
            self.state_manager.current.update(elapsed)
            self.screen.clear()
            self.state_manager.current.draw(self.screen.surf)
            if self.debug_renderer:
                self.debug_renderer()
            else:
                # empty the debugging stack ourselves
                debugstack.clear()
            self.screen.update()


class Label:

    def __init__(self, text):
        self.text = text


class Button(Label):

    def __init__(self, text, callback):
        super().__init__(text)
        self.callback = callback


class LabelSprite(pg.sprite.Sprite):

    def __init__(self, label, font, *groups):
        super().__init__(*groups)
        self.label = label
        self.font = font
        self.image = self.font.render(self.label.text, True, (200,200,200))
        self.rect = self.image.get_rect()


class ButtonSprite(pg.sprite.Sprite):

    def __init__(self, button, font, *groups):
        super().__init__(*groups)
        self.button = button
        self.font = font
        textimage = self.font.render(self.button.text, True, (200,200,200))
        textrect = textimage.get_rect().inflate(20,20)
        self.image = pg.Surface(textrect.size)
        self.rect = self.image.get_rect()
        self.image.blit(textimage, textimage.get_rect(center=self.rect.center))
        pg.draw.rect(self.image, (60,60,60), self.rect, 1)


class MenuState(State):
    "Vertical list of menu items"

    def __init__(self, space, font, items):
        self.space = space
        self.sprites = pg.sprite.Group()
        class_map = {Label: LabelSprite, Button: ButtonSprite}
        for item in items:
            class_ = class_map[type(item)]
            class_(item, font, self.sprites)
        sprites = self.sprites.sprites()
        for s1, s2 in zip(sprites[:-1], sprites[1:]):
            s2.rect.top = s1.rect.bottom + 20
        bounding = wrap(sprite.rect for sprite in sprites)
        dx, dy = (space.centerx - bounding.centerx,
                  space.centery - bounding.centery)
        for sprite in sprites:
            sprite.rect.x += dx
            sprite.rect.y += dy

    def do_callback(self, button):
        if button.callback:
            button.callback()

    def draw(self, surf):
        self.sprites.draw(surf)
        if self.hover:
            pg.draw.rect(surf, (200,10,10), self.hover.rect, 1)

    def enter(self):
        pg.mouse.set_visible(True)
        self.select_first_button()

    def handle(self, event):
        if event.type == pg.KEYDOWN:
            self.on_keydown(event)
        elif event.type == pg.MOUSEBUTTONDOWN:
            self.on_mousebuttondown(event)
        elif event.type == pg.MOUSEMOTION:
            self.on_mousemotion(event)

    def on_keydown(self, event):
        if event.key == pg.K_RETURN:
            if self.hover:
                self.do_callback(self.hover.button)
        elif event.key == pg.K_DOWN:
            self.selection(1)
        elif event.key == pg.K_UP:
            self.selection(-1)

    def on_mousebuttondown(self, event):
        sprites = (sprite for sprite in self.sprites if isinstance(sprite, ButtonSprite))
        for sprite in sprites:
            if sprite.rect.collidepoint(event.pos):
                self.do_callback(self.hover.button)
                break

    def on_mousemotion(self, event):
        sprites = (sprite for sprite in self.sprites if isinstance(sprite, ButtonSprite))
        for sprite in sprites:
            if sprite.rect.collidepoint(event.pos):
                self.hover = sprite
                break
        else:
            self.hover = None

    def select_first_button(self):
        for sprite in self.sprites:
            if isinstance(sprite, ButtonSprite):
                self.hover = sprite
                pg.mouse.set_pos(self.hover.rect.center)
                break

    def selection(self, move):
        if not self.hover:
            self.select_first_button()
        if self.hover:
            sprites = tuple(sprite for sprite in self.sprites if isinstance(sprite, ButtonSprite))
            index = sprites.index(self.hover)
            sprite = sprites[(index + move) % len(sprites)]
            # set_pos fires mouse motion to update hovered button
            pg.mouse.set_pos(sprite.rect.center)

    def update(self, elapsed):
        self.sprites.update(elapsed)


class lerpvalue:

    def __init__(self, a, b, duration):
        if isinstance(a, lerpvalue):
            a = a.current
        if isinstance(b, lerpvalue):
            b = b.current
        self.a = a
        self.b = b
        self.duration = duration
        self.time = 0

    @property
    def current(self):
        return lerp(self.a, self.b, self.time / self.duration)

    def update(self, elapsed):
        if self.time < self.duration:
            self.time += elapsed
            if self.time > self.duration:
                self.time = self.duration


class Wordbag:
    "Stack like word container"

    def __init__(self, words):
        self.words = words
        self._sample = None

    def __bool__(self):
        return bool(self._sample)

    def __len__(self):
        return len(self._sample)

    def pop(self):
        return self._sample.pop()

    def randomize(self, k, predicate=None):
        if predicate is None:
            predicate = lambda word: True
        population = set(word for word in self.words if predicate(word))
        self._sample = random.sample(population, k)


class Gameplay(State):

    def __init__(self, space, spawn_area, wordbag, font, levels, skip_intro=False):
        self.space = space
        self.spawn_area = spawn_area
        self.wordbag = wordbag
        self.font = font
        # levels: (k population, predicate) indexed by difficulty.
        self.levels = levels
        self.skip_intro = skip_intro
        self.player = PlayerSprite((space.centerx, 3*space.height/4))
        self.group = pg.sprite.LayeredUpdates()
        self.paused = False
        self.updatestack = []
        self.readysprite = pg.sprite.Sprite()
        self.readysprite.image = self.font.render('Get Ready', True, (200,200,200))
        self.readysprite.rect = self.readysprite.image.get_rect()
        self.readysprite.time = 0
        self.damage_on_miss = False
        self.level = 0

    def back_to_mainmenu(self):
        # assumes we're in a sub menu
        # pop menu
        popstate()
        # pop self
        popstate()

    def _add_sparks(self, sparks):
        self.group.add(*sparks)

    def check_win_state(self):
        # check for win state
        if len(self.wordbag) == 0 and self.is_win_state():
            self.clear_explosions()
            if self.level + 1 == len(self.levels):
                # last level completed
                pushstate(
                    MenuState(self.space, self.font,
                              (Label('A Winner is You!'),
                               Button('Restart', popstate),
                               Button('Main menu', self.back_to_mainmenu),
                               Button('Exit to desktop', quit))))
            else:
                # Next level
                self.paused = False
                self.level += 1
                self.enter()

    def clear_explosions(self):
        for key in set(cooldowns):
            if isinstance(key, Explosion):
                del cooldowns[key]

    def draw(self, surf):
        for sprite in self.group:
            if isinstance(sprite, TextSprite):
                rect = sprite.rect.clamp(self.space)
            else:
                rect = sprite.rect
            surf.blit(sprite.image, rect)
        healthpip = pg.Rect(0, self.space.bottom - 30, 20, 20)
        for i in range(self.player.health):
            healthpip.x = 10 + healthpip.width * i * 1.5
            pg.draw.rect(surf, (200,10,10), healthpip)

    def enter(self):
        pg.mouse.set_visible(False)
        if not self.paused:
            # not entering from paused state
            self.reset()
        self.paused = False

    def exit_intro(self):
        self.group.remove(self.readysprite)
        self.updatestack.pop()

    def fire(self, letter):
        if not self.locked:
            for textsprite in (sprite for sprite in self.group
                               if isinstance(sprite, TextSprite)):
                if textsprite.text and letter == textsprite.text[0]:
                    self.locked = textsprite
                    break
            else:
                self.locked = None
        if self.locked:
            if letter == self.locked.text[0]:
                self.locked.text = self.locked.text[1:]
                # NOTE: self.locked EnemyShipSprite, might have killed itself by now
                if self.group.has(self.locked):
                    self.group.move_to_front(self.locked)
                self.locked.color = (200, 200, 10)
                self.locked.background = (45,45,45,200)
                # add bullet
                bulletsprite = BulletSprite(self.locked.enemyshipsprite)
                bulletsprite.position = self.player.position
                self.group.add(bulletsprite)
                if not self.locked.text:
                    self.locked = None
            elif self.damage_on_miss:
                self.hit_player()

    def handle(self, event):
        if event.type == pg.KEYDOWN:
            self.on_keydown(event)

    def hit_player(self):
        self.player.health -= 1
        if self.player.health == 0:
            self.paused = False
            popstate()
            items = (Label('Game Over'),
                     Button('Restart', lambda:pushstate(self)),
                     Button('Exit to desktop', quit))
            deathstate = MenuState(self.space, self.font, items)
            pushstate(deathstate)

    def is_win_state(self):
        """
        If no textsprites, nothing left in wordbag, we're not waiting for
        cooldown, and no explosions happening--player has won!
        """
        return (not self.wordbag
                and cooldowns[self.spawn_word] <= 0
                and not any(True for sprite in self.group
                            if isinstance(sprite, (TextSprite, Spark))))

    def needs_word_spawn(self):
        ntextsprites = sum(1 for sprite in self.group if isinstance(sprite, TextSprite))
        return (ntextsprites < self.max_nsprites
                and self.wordbag
                and cooldowns[self.spawn_word] <= 0)

    def on_keydown(self, event):
        if event.key == pg.K_ESCAPE:
            self.paused = True
            pausestate = MenuState(self.space, self.font,
                    (Label('Paused'),
                     Button('Resume', popstate),
                     Button('Main menu', self.back_to_mainmenu),
                     Button('Exit to desktop', quit)))
            pushstate(pausestate)
        else:
            self.fire(event.unicode)

    def remove_sparks_outofbounds(self):
        # remove any sparks that are out of bounds
        for spark in (sprite for sprite in self.group if isinstance(sprite, Spark)):
            if not self.space.contains(spark.rect):
                spark.kill()

    def reset(self):
        self.group.empty()
        self.max_nsprites = 3
        self.locked = None
        if self.level > 0:
            self.readysprite.image = self.font.render(f'Wave {self.level+1}', True, (200,200,200))
            # place it off screen
            self.readysprite.rect = self.readysprite.image.get_rect(topleft=(-1000,-1000))
        k, predicate = self.levels[self.level]
        self.wordbag.randomize(k, predicate)
        self.player.reset()
        self.group.add(self.player)
        self.updatestack.clear()
        self.updatestack.append(self.update_gameplay)
        self.updatestack.append(self.update_intro)
        self.readysprite.time = 0
        self.group.add(self.readysprite)
        if self.skip_intro:
            self.exit_intro()

    def spawn_explosions_from_deaths(self, died):
        # spawn explosions where bullets and enemy ships died
        for sprite in died:
            if isinstance(sprite, BulletSprite):
                explosion = Explosion(sprite.position, 10, (200,)*3, (15,25))
                self._add_sparks(explosion.sparks)
            elif isinstance(sprite, EnemyShipSprite):
                explosion = Explosion(sprite.rect.center, 600, (200,10,10), (5,10))
                # wait a bit before exploding enemy ship
                cooldowns[explosion] = 500

    def spawn_explosions_from_cooldowns(self):
        # add any sparks from an explosion whose cooldown is ready
        for key, cooldown in cooldowns.items():
            if (isinstance(key, Explosion)
                    and not any(sprite for sprite in self.group
                                if isinstance(key, Explosion) and sprite == key)
                    and cooldown <= 0):
                self._add_sparks(key.sparks)

    def spawn_word(self):
        word = self.wordbag.pop()
        textsprite = TextSprite(word, (200,200,200), self.font, (45,45,45,127))
        textsprite._layer = 10
        self.group.add(textsprite, textsprite.enemyshipsprite)
        # place the textsprite randomly in the spawn area
        rect = random_location(textsprite.rect, self.spawn_area)
        textsprite.enemyshipsprite.position = rect.center
        cooldowns[self.spawn_word] = 1000

    def update(self, elapsed):
        self.updatestack[-1](elapsed)

    def update_intro(self, elapsed):
        self.group.update(elapsed)
        self.readysprite.time += .02
        debug(f'time: {self.readysprite.time:.2f}')
        if self.readysprite.time < 1:
            t, _ = math.modf(self.readysprite.time)
            self.readysprite.rect.center = lerpi(
                    (-self.space.right, self.space.centery),
                    self.space.center, t)
        elif self.readysprite.time < 2:
            pass
        elif self.readysprite.time < 3:
            t, _ = math.modf(self.readysprite.time)
            self.readysprite.rect.center = lerpi(
                    self.space.center, (self.space.right * 2, self.space.centery), t)
        else:
            self.exit_intro()

    def update_gameplay(self, elapsed):
        if self.needs_word_spawn():
            self.spawn_word()
        self.remove_sparks_outofbounds()
        died = set(sprite for sprite in self.group
                   if isinstance(sprite, (BulletSprite, EnemyShipSprite))
                   and sprite.alive())
        self.group.update(elapsed)
        died = set(sprite for sprite in died if not sprite.alive())
        self.spawn_explosions_from_deaths(died)
        self.spawn_explosions_from_cooldowns()
        enemyshipsprites = set(sprite for sprite in self.group
                               if isinstance(sprite, EnemyShipSprite))

        if self.locked:
            # point player at enemy
            angle = abs_angle_to(self.player.position, self.locked.enemyshipsprite.position)
            self.player.angle = math.degrees(angle)

        if not enemyshipsprites and self.is_win_state():
            # all enemies dead, wait for animations
            self.player.angle = 90
            self.updatestack.pop()
            self.updatestack.append(self.update_gameplay_wait_for_animations)
        else:
            # move and point enemy ships at player
            for enemyshipsprite in enemyshipsprites:
                x, y = enemyshipsprite.position
                angle = abs_angle_to((x,y), self.player.position)
                enemyshipsprite.angle = math.degrees(angle)
                enemyshipsprite.position = (x + math.cos(angle) * 1, y + math.sin(-angle) * 1)
                x, y = enemyshipsprite.position
                enemyshipsprite.textsprite.rect.midtop = (
                    x, y + enemyshipsprite.textsprite.rect.height / 2)
                # check player collision
                if (cooldowns['player-hit'] <= 0
                        and enemyshipsprite.rect.colliderect(self.player.rect)):
                    enemyshipsprite.kill()
                    enemyshipsprite.textsprite.kill()
                    cooldowns['player-hit'] = 1000
                    self.player.health -= 1
                    if self.player.health == 0:
                        # player died
                        pushstate(
                            MenuState(self.space, self.font,
                                      (Label('You Died'),
                                       Button('Restart', popstate),
                                       Button('Main menu', self.back_to_mainmenu),
                                       Button('Exit to desktop', quit))))
                    # no need to check anymore because we've applied the cooldown
                    break

    def update_gameplay_wait_for_animations(self, elapsed):
        died = set(sprite for sprite in self.group
                   if isinstance(sprite, (BulletSprite, EnemyShipSprite))
                   and sprite.alive())
        self.group.update(elapsed)
        died = set(sprite for sprite in died if not sprite.alive())
        self.remove_sparks_outofbounds()
        self.spawn_explosions_from_deaths(died)
        self.spawn_explosions_from_cooldowns()
        self.check_win_state()


class PlayerSprite(pg.sprite.Sprite):

    def __init__(self, position, *groups):
        super().__init__(*groups)
        self.position = position
        self.angle = 90
        self._image = pg.Surface((32,)*2,pg.SRCALPHA)
        self.rect = self._image.get_rect(center=self.position)
        rect = self._image.get_rect()
        points = [rect.midright, rect.bottomleft, rect.topleft]
        pg.draw.polygon(self._image, (10,10,200), points)
        self.reset()

    def reset(self):
        self.health = 3
        self.angle = 90
        self.update_image()

    def update_image(self):
        self.image = pg.transform.rotate(self._image, self.angle)

    def update(self, elapsed):
        self.rect.center = self.position
        self.image = pg.transform.rotate(self._image, self.angle)


class BulletSprite(pg.sprite.Sprite):

    def __init__(self, target, *groups):
        super().__init__(*groups)
        self.target = target
        self.image = pg.Surface((10,10), pg.SRCALPHA)
        self.rect = self.image.get_rect()
        pg.draw.circle(self.image, (200,10,10,127), self.rect.center, self.rect.width//2)
        self.position = self.rect.center
        self.accumulator = 0
        self.timetolive = 500
        self.original_position = None

    def update(self, elapsed):
        if self.original_position is None:
            self.original_position = self.position
        self.accumulator += elapsed
        self.position = lerpi(self.original_position, self.target.position,
                (self.accumulator / self.timetolive))
        self.rect.center = self.position
        if self.accumulator >= self.timetolive:
            self.kill()
            angle = abs_angle_to(self.original_position, self.target.position)
            # knock target back
            x, y = self.target.position
            force = 4
            newposition = (x + math.cos(angle) * force, y + math.sin(-angle) * force)
            self.target.position = newposition
            if not self.target.textsprite.text:
                self.target.kill()
                self.target.textsprite.kill()


class Spark(pg.sprite.Sprite):

    __slots__ = ('image', 'rect', 'x', 'y', 'dx', 'dy')

    def __init__(self, size, position, angle, speed, color, *groups):
        super().__init__(*groups)
        self.image = pg.Surface(size, pg.SRCALPHA)
        self.rect = self.image.get_rect()
        pg.draw.circle(self.image, color, self.rect.center, min(self.rect.size)//2)
        self.x, self.y = position
        self.dx = math.cos(angle) * speed
        self.dy = math.sin(-angle) * speed

    def update(self, elapsed):
        self.x += self.dx
        self.y += self.dy
        self.rect.center = (self.x, self.y)


class Explosion:

    def __init__(self, center, nsparks, color, speeds=None):
        self.center = center
        sizes = [(s,s) for s in range(1,3)]
        angles = range(360)
        if speeds is None:
            speeds = (10, 20)
        minspeed, maxspeed = speeds
        def randomspark_args():
            return (random.choice(sizes), self.center,
                    math.radians(random.choice(angles)),
                    random.uniform(minspeed, maxspeed), color)
        sparkargs = set(randomspark_args() for _ in range(nsparks))
        sprites = (Spark(*args) for args in sparkargs)
        self.sparks = pg.sprite.Group(*sprites)


class EnemyShipSprite(pg.sprite.Sprite):

    def __init__(self, textsprite, size, *groups):
        super().__init__(*groups)
        self.textsprite = textsprite
        self._angle = 180
        self._image = pg.Surface(size, pg.SRCALPHA)
        rect = self._image.get_rect()
        # random points on each side of rect
        points = [
            (random.randint(rect.left, rect.right), rect.top),
            (rect.right, random.randint(rect.top, rect.bottom)),
            (random.randint(rect.left, rect.right), rect.bottom),
            (rect.left, random.randint(rect.top, rect.bottom))
        ]
        pg.draw.polygon(self._image, (200,150,10), points)
        self.update_image()
        self.rect = self.image.get_rect()
        self._position = self.rect.center

    @property
    def angle(self):
        return self._angle

    @angle.setter
    def angle(self, value):
        self._angle = value
        self.update_image()

    @property
    def position(self):
        return self._position

    @position.setter
    def position(self, value):
        self.rect.center = self._position = value

    def update_image(self):
        self.image = pg.transform.rotate(self._image, self._angle)


class TextSprite(pg.sprite.Sprite):

    def __init__(self, text, color, font, background, *groups, padding=(20, 10)):
        super().__init__(*groups)
        self._text = text
        self._color = color
        self._font = font
        self._background = background
        self._padding = padding
        textrect = pg.Rect((0,0), self._font.size(self._text))
        self._image = pg.Surface(textrect.inflate(*self._padding).size, pg.SRCALPHA)
        self.rect = self._image.get_rect()
        self.position = self.rect.center
        self._update_image()
        self.enemyshipsprite = EnemyShipSprite(self, (32,32))

    def _update_image(self):
        textimage = self._font.render(self._text, True, self._color)
        self._image.fill(self._background)
        px, py = self._padding
        rect = self._image.get_rect()
        pos = textimage.get_rect(right=rect.right-px//2, top=rect.top+py//2)
        self._image.blit(textimage, pos)
        self.image = self._image

    @property
    def text(self):
        return self._text

    @text.setter
    def text(self, value):
        self._text = value
        self._update_image()

    @property
    def color(self):
        return self._color

    @color.setter
    def color(self, value):
        self._color = value
        self._update_image()

    @property
    def font(self):
        return self._font

    @font.setter
    def font(self, value):
        self._font = value
        self._update_image()

    @property
    def padding(self):
        return self._padding

    @padding.setter
    def padding(self, value):
        self._padding = value
        self._update_image()

    @property
    def background(self):
        return self._background

    @background.setter
    def background(self, value):
        self._background = value
        self._update_image()


class DebugRenderer:

    def __init__(self, screen):
        self.screen = screen
        self.font = pg.font.Font(None, 24)
        self.initial_previous = rectat(self.screen.rect, bottom=self.screen.rect.top)

    def __call__(self):
        prev = self.initial_previous
        while debugstack:
            value = debugstack.pop()
            if isinstance(value, str):
                image = self.font.render(value, True, (200,10,10))
                prev = image.get_rect(topright = prev.bottomright)
                self.screen.surf.blit(image, prev)
            else:
                try:
                    func, *args = value
                except TypeError:
                    pass
                else:
                    if callable(func):
                        func(self.screen.surf, *args)


def start(debug=False, skip_mainmenu=False, skip_intro=False):
    "Setup and start the game"
    with open('words.txt') as words_f:
        words = words_f.read().splitlines()
    wordbag = Wordbag(words)
    npass, nfail = pg.init()
    if nfail:
        print(f'pass: {npass}, fail: {nfail}')
    clock = Clock(60)
    screen = Screen((500, 900))
    state_manager = StateManager()
    font = pg.font.Font(None, 32)
    font_height = font.get_height()
    spawn_area = screen.rect.copy()
    spawn_area.width *= 1.25
    spawn_area.height = font_height * 2
    spawn_area.centerx = screen.rect.centerx
    spawn_area.bottom = screen.rect.top
    # (sample size, predicate)
    levels = [(5, lambda word: not haspunctuation(word) and 1 < len(word) < 5),
              (10, lambda word: not haspunctuation(word) and 2 < len(word) < 5),
              (15, lambda word: not haspunctuation(word) and 3 < len(word) < 5),
              (20, lambda word: not haspunctuation(word) and len(word) > 4),
              (20, lambda word: not haspunctuation(word) and len(word) > 7)]
    gameplay = Gameplay(screen.rect, spawn_area, wordbag, font, levels, skip_intro=skip_intro)
    mainmenu = MenuState(screen.rect, font,
                         (Label('PyType'),
                          Button('Play', lambda: pushstate(gameplay)),
                          Button('Exit to desktop', popstate)))
    if debug:
        debug_renderer = DebugRenderer(screen)
    else:
        debug_renderer = None
    engine = Engine(clock, screen, state_manager, debug_renderer=debug_renderer)
    if skip_mainmenu:
        pushstate(gameplay)
    else:
        pushstate(mainmenu)
    engine.run()

def main(argv=None):
    "Typing game inspired by ZType"
    parser = argparse.ArgumentParser(description=main.__doc__)
    parser.add_argument('--debug', action='store_true', help='Show debugging info on screen.')
    parser.add_argument('--skip-mainmenu', action='store_true')
    parser.add_argument('--skip-intro', action='store_true')
    args = parser.parse_args(argv)
    start(debug=args.debug, skip_mainmenu=args.skip_mainmenu, skip_intro=args.skip_intro)

if __name__ == '__main__':
    main()
