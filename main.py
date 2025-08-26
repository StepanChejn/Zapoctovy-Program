import sounddevice as sd
from app import *

# Values used to update playback progress bar
pb_value = 0

def callback(outdata, frames, time, status):
    """ Called periodically by sounddevice's OutputStream
    
    returns piece of audio (zero array if paused) that is used by OutputStream
    to play back the audio snippets
    """
    global application, pb_value

    # If audio is paused return a zero array
    if not application.is_playing or application.out_data is None:
        outdata.fill(0)
        return

    block_end = application.i + frames

    # Copy a block from the out_data array
    if block_end <= application.pb_end_index:
        block = application.out_data[application.i : block_end]
        application.i = block_end
    # If a block is partly in the loop but partly outside, split it and wrap the second part back
    else:
        first_part = application.out_data[application.i: application.pb_end_index]
        remaining_part_len = block_end - application.pb_end_index
        second_part = application.out_data[application.pb_start_index : application.pb_start_index + remaining_part_len]
        block = np.concatenate((first_part, second_part), axis=0)

        application.i = application.pb_start_index + remaining_part_len

    # copy block into output
    outdata[:, 0] = block

    # Update progress bar value
    orig_sample_index = application.start_index + application.i / application.stretch_factor
    pb_value = orig_sample_index / application.file_len


def playback_progress(application):
    """Updates progress bar and timecode every 33 milliseconds"""
    global pb_value, root

    v = pb_value  # in Tk main thread
    application.update_time(v)
    root.after(33, playback_progress, application)  # around 30 times per second


# Loads application
root = Tk()
root.title("Phase Vocoder")
application = App(root)

# Initialise and start audio stream
stream = sd.OutputStream(callback=callback, samplerate=application.samplerate, blocksize=application.out_blocksize, channels=1)
stream.start()

# Start GUI main loop
playback_progress(application)
try:
    root.mainloop()
finally:
    stream.stop()
    stream.close()
