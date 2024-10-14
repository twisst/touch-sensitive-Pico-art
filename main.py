# touch met synth

import time
import board
import touchio
from adafruit_debouncer import Debouncer

import digitalio
import synthio
import audiopwmio
import audiomixer
import asyncio

import neopixel
from rainbowio import colorwheel
neopixel_led = neopixel.NeoPixel(board.GP21, 1, brightness=0.4)

touch_pins = (board.GP15, board.GP9, board.GP5, board.GP0) # pins 20, 12, 7 and 1 on Pico's left side
buttons = []   # will hold list of Debouncer objects

## stuff for  the theremin part ##

theremin = False # to set when GP15 is actually connected
max_th = 100 # finding the max value we're seeing coming in

# a little helper class for noise filtering when using
class RunningAverage:
    def __init__(self,count):
        self.count = count
        self.i = 0
        self.buf = [0] * self.count
    def add_value(self,val):
        self.buf[self.i] = val
        self.i = (self.i + 1) % self.count
    def average(self):
        return sum(self.buf)/self.count
    
# Will return an integer between out_min and out_max
# credits: https://forum.micropython.org/viewtopic.php?t=7615
def convert(x, i_m, i_M, o_m, o_M):
    return max(min(o_M, (x - i_m) * (o_M - o_m) // (i_M - i_m) + o_m), o_m)    

## end theremin part ##

# wait for things to stabilize before creating touch pins so their raw_value baseline are okay
time.sleep(1.0)

for pin in touch_pins:   # set up each pin
    try:
        tmp_pin = touchio.TouchIn(pin)
        if pin == board.GP0: # if the top-left pin is also connected, then set it up as a theremin.
            theremin = True
            there_pin = tmp_pin
            base = int(there_pin.raw_value * 1.02) # find a threshold value
            avg = RunningAverage(8) # start averaging values
            th = 0
            print(pin, "is connected for theremin")
        else:
            buttons.append( Debouncer(tmp_pin) )
            print(pin, "is connected")
    except ValueError as e:
        print(e)
        print(pin, "is NOT connected")

audio = audiopwmio.PWMAudioOut(board.GP16)
# mixer = audiomixer.Mixer(channel_count=1, sample_rate=22050, buffer_size=2048)
synth = synthio.Synthesizer(sample_rate=22050)

audio.play(synth)

# built-in LED
led = digitalio.DigitalInOut(board.LED)
led.direction = digitalio.Direction.OUTPUT
# blink a few times to show that the script has started
# for i in range(4):
#     led.value = True
#     time.sleep(0.1)
#     led.value = False
#     time.sleep(0.1)
led.value = True
time.sleep(0.1)
led.value = False

class Interval:
    """Simple class to hold an interval value. Use .value to to read or write."""

    def __init__(self, initial_interval):
        self.value = initial_interval
        
class Colours:
    """
    Simple class to hold colour values for the neopixel LED.
    Format is [0, 0, 0, 0] for rainbow, red, green, blue
    Use .values to to read or write.
    """

    def __init__(self, initial_colours):
        self.values = initial_colours


async def playTheremin(theremin, max_th, colours, interval):
    
    while theremin:
        
        # theremin-like synth
        avg.add_value( there_pin.raw_value )
        th = 0
        th = min(max(avg.average()-base, 0), max_th)
        
        if avg.average() > max_th:
            max_th = avg.average()
            
        if th > base:   # hand present

            #         note = convert(th.raw_value, 0, 10000, 0, 120)
            #         note_new = note_base + int(th/4)
            #         note = int(convert(th, 0, 5000, 0, 120))
            note = int(convert(th, 0, max_th, 10, 124))
            print(f"/*{there_pin.raw_value}*/") # printing the raw values formatted to work with Serial Studio
            synth.press(note)
            
            colours.values[3] = 1 # a bit messy to do this from here, but also turn on the Neopixel rainbow effect
            
            await asyncio.sleep(0.05)
            synth.release(note)
            
        else:
            # when still on when there is no hand, turn off the rainbow effect and the built-in LED
            if colours.values[3] > 0:
                colours.values[3] = 0
                interval.value = 0
        
        await asyncio.sleep(0)

async def arpeggio():  # playing all notes up and down the MIDI range

    # up all MIDI notes
    for j in range(10, 124, 3):
        synth.press(j)
        await asyncio.sleep(0.02)
        synth.release(j)
    # down all MIDI notes
    for j in range(124, 10, -3):
        synth.press(j)
        await asyncio.sleep(0.02)
        synth.release(j)


async def bleepUp(): # bliep up
    
    for i in range(12, 120, 12):
        synth.press(i)
        await asyncio.sleep(0.02)
        synth.release(i)

# async def bleepDown(): # bliep down
#     
#     for i in range(80, 10, -2):
#         synth.press(i)
#         await asyncio.sleep(0.02)
#         synth.release(i)

async def threeArpeggios():
    
    notes = [196, 294, 392, 494, 587, 220, 330, 440, 523, 659, 262, 392, 523, 659, 784]
    for i in range(len(notes)):
        note = synthio.Note(notes[i])
        synth.press(note)
        await asyncio.sleep(0.03)
        synth.release(note)
        await asyncio.sleep(0.01)
        
        if i % 5 == 4:
            await asyncio.sleep(0.2)


async def checkButtons(interval, colours):

    while True:
        
        # check on all buttons
        for i in range(len(buttons)):
            buttons[i].update()
            
            # when a button is pressed...
            if buttons[i].rose:

                if i == 0: # turn built-in LED on when the first button is pressed
                    
                    interval.value = 0.2
                    
                    play_task = asyncio.create_task(threeArpeggios())
                
                elif i == 1: # play up and down arpeggio when the second button is pressed
                    
                    interval.value = 0.1
                    
                    play_task = asyncio.create_task(arpeggio())

                elif i == 2:
                    
                    interval.value = 0.03
                    
                    play_task = asyncio.create_task(bleepUp())

                colours.values[i] = 1 # show us the colours!
                    
            # when a button is released...
            if buttons[i].fell:
                
                interval.value = 0 # turn the built-in LED off
                
                colours.values[i] = 0 # turn off this colour (or rainbow)
                
        # Let another task run.
        await asyncio.sleep(0)


async def blink(led, interval):
    """Blink the given pin forever.
    The blinking rate is controlled by the supplied Interval object.
    """
    
    mode = 0

    while True:
        
        if 0 < interval.value < 1:
            
            led.value = not led.value
            await asyncio.sleep(interval.value)

        elif mode != interval: # only do something when the interval just changed:

            led.value = interval.value
                
            mode = interval.value
        
        await asyncio.sleep(0)


async def changeNeopixel(np, colours, interval):
    """
    Change colours on the neopixel LED
    """
    
    while True:
        
        # if rainbow is active, change the colours of the Neopixel LED
        if colours.values[3] != 0:
            
            neopixel_led.fill( colorwheel((time.monotonic()*90)%255) )
            
            interval.value = 1 # bit messy to do this from here, but also turn on the built-in LED
            
        else: # check if other colours are activated
            
            for i in range(3): # so r, g and b

                if colours.values[i] > 0:
                
                    colours.values[i] = colours.values[i] + 2
              
            neopixel_led.fill((colours.values[0], colours.values[1], colours.values[2])) # show changes in Neopixel LED
        
        await asyncio.sleep(0)
        

async def main():
    
    interval = Interval(0) # to change the speed of blinking the on-board LED
    colours = Colours([0, 0, 0, 0]) # initial values for rainbow, red, green, blue
    
    check_buttons_task = asyncio.create_task(checkButtons(interval, colours))
    blink_task = asyncio.create_task(blink(led, interval))
    neopixel_task = asyncio.create_task(changeNeopixel(neopixel_led, colours, interval))
    theremin_task = asyncio.create_task(playTheremin(theremin, max_th, colours, interval))
    
    await asyncio.gather(check_buttons_task, blink_task, neopixel_task, theremin_task)
    


asyncio.run(main())
    
