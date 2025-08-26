import soundfile as sf
from tkinter import *
from tkinter import ttk
from tkinter import filedialog
from audio_processing import *
import os

class App:
    """Class handling GUI, playback and setting logic"""
    def __init__(self, root: Tk):
        self.file_path = None
        self.file_name = "" 

        self.is_playing = False

        # Array used for audio playback
        self.out_data = None

        self.stretch_factor = 1.0
        self.pitch_factor = 1.0

        # Where does the selected segment start and end in percentage of the file length
        self.start_factor = 0.0
        self.end_factor = 1.0

        self.file_len = None
        self.samplerate = None

        # Flags for detecting changes in settings
        self.param_change = False
        self.loop_change = False

        # Indexes of the original data array for the selected segment
        self.start_index = None
        self.end_index = None

        # Indexes of the out_data array for the selected segment
        self.pb_start_index = None
        self.pb_end_index = None
        
        # Index of the start of currently playing chunk of audio
        self.i = None

        # Size of the chunk of audio requested by callback function for OutputStream in main.py
        self.out_blocksize = 1024
        
        # Prepare gui and open a sound file
        self.build_gui(root)
        self.openfile()


    def build_gui(self, root: Tk):
        # Root is the parent node of every piece of the gui
        self.root = root
        self.root.geometry("600x480")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        self.root.resizable(False, False)

        # Frame is a child of root, which will have all other elements as children
        self.frame = Frame(self.root)
        self.frame.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        for i in range(7):
            self.frame.rowconfigure(i, weight=1)
        for i in range(4):
            self.frame.columnconfigure(i, weight=1)

        # Now we define all other elements - buttons, sliders etc.
        # File selection
        self.file_button = Button(self.frame, text="Select file", command=self.openfile)
        self.file_button.grid(row=0, column=1)

        # File label
        self.title = Label(self.frame, text="File: ")
        self.title.grid(row=0, column=2, sticky="ew")
        
        # Time
        self.time = Label(self.frame, text="Time: 00:00:000")
        self.time.grid(row=1, column=0, sticky="w")

        # Visualise playback
        self.pb_bar = ttk.Progressbar(self.frame, value=self.i, 
                                      mode="determinate", maximum=100, orient="horizontal")
        self.pb_bar.grid(row=1, column=1, columnspan=3, sticky="ew")

        # Pitch shift factor
        self.pitch_label = Label(self.frame, text="Pitch Shift Factor:")
        self.pitch_label.grid(row=2, column=0, sticky="w")

        self.pitch_slider = Scale(self.frame, from_=0.5, to=1.5,
                                resolution=0.001, command=self.update_settings,
                                orient=HORIZONTAL)
        self.pitch_slider.grid(row=2, column=1, columnspan=2, sticky="ew")
        self.pitch_slider.set(1.0)

        self.reset_button1 = Button(self.frame, text="Reset", command=self.reset_pitch)
        self.reset_button1.grid(row=2, column=3, sticky="ew")

        # Time stretch factor
        self.stretch_label = Label(self.frame, text="Time Stretch Factor:")
        self.stretch_label.grid(row=3, column=0, sticky="w")

        self.stretch_slider = Scale(self.frame, from_=0.5, to=1.5,
                                    resolution=0.001, command=self.update_settings,
                                    orient=HORIZONTAL)
        self.stretch_slider.grid(row=3, column=1, columnspan=2, sticky="ew")
        self.stretch_slider.set(1.0)

        self.reset_button2 = Button(self.frame, text="Reset", command=self.reset_time)
        self.reset_button2.grid(row=3, column=3, sticky="ew")

        # Create start time slider
        self.start_label = Label(self.frame, text="Start: 00:00:000")
        self.start_label.grid(row=4, column=0, sticky="w")

        self.start_slider = Scale(self.frame, from_=0.0, to=1, 
                                  resolution=0.001, command=self.update_start,
                                  orient=HORIZONTAL)
        self.start_slider.grid(row=4, column=1, columnspan=3, sticky="ew")

        # Create end time slider
        self.end_label = Label(self.frame, text="End: 00:00:000")
        self.end_label.grid(row=5, column=0, sticky="w")

        self.end_slider = Scale(self.frame, from_=0.0, to=1,
                                  resolution=0.001, command=self.update_end,
                                  orient=HORIZONTAL)
        self.end_slider.grid(row=5, column=1, columnspan=3, sticky="ew")
        self.end_slider.set(1.0)
        
        # Pause and rewind button
        self.pause_button = Button(self.frame, text="Play", command=self.pause, height= 1, width= 6)
        self.pause_button.grid(row=6, column=1, columnspan=1)

        self.rewind_button = Button(self.frame, text="Rewind", command=self.rewind, height=1, width=6)
        self.rewind_button.grid(row=6, column=2,  columnspan=1)


    def openfile(self, value=None):
        """Opens a sound file and initialises AudioProcessor and all internal attributes"""

        if self.is_playing:
            self.pause()

        self.file_path = filedialog.askopenfilename(initialdir = os.getcwd(),
                                          title = "Select a File",
                                          filetypes = [("WAV", "*.wav"),
                                                       ("FLAC", "*.flac"),
                                                        ("MP3", "*.mp3")])
        if not self.file_path:
            return
        
        # Extract file name from its path
        self.file_name = self.file_path.split("/")[-1]
        self.title["text"] = "File: " + self.file_name
        
        # Open sound file, convert all files to mono and initialise AudioProcessor
        d, sr = sf.read(self.file_path, dtype="float32", always_2d=True)
        d = np.mean(d, axis=1)
        self.AP = AudioProcessor(d, sr)


        self.samplerate = sr

        self.file_len = len(d)

        self.start_index = 0
        self.pb_start_index = 0

        self.end_index = self.file_len - 1
        self.pb_end_index = int(round(self.end_index * self.stretch_factor))
        
        self.i = 0
        self.loop_size = self.file_len - 1
        
        
        self.update_settings()
        self.update_start(0.0)
        self.update_end(1.0)
        self.update_time(0.0)


    def pause(self):
        """Handles switching is_playing and also recomputing out_data if needed"""
        # If any setttings changed we figure out if we need to recompute the whole array
        # or just change the playback start and end indexes
        if not self.is_playing and (self.param_change or self.loop_change):
            self.pause_button.config(text="Loading")
            self.pause_button.update_idletasks()

            recompute = False

            # read slider values once and convert them into indexes of the original audio array
            s = int(self.start_slider.get() * self.file_len)
            e = int(self.end_slider.get() * self.file_len)

            if e > self.file_len:
                e = self.file_len

            # If only indexes change and time and pitch factors stay the same,
            # we might not need to recompute out_data
            if self.loop_change and (not self.param_change):

                # Convert start and end indexes into indexes of out_data array
                ps = int(round((s - self.start_index) * self.stretch_factor))
                pe = int(round((e - self.start_index) * self.stretch_factor))

                # Clamp to the actual out_data bounds
                ps = max(ps, 0)
                pe = min(pe, len(self.out_data))

                loop_len = pe - ps

                # Check if indexes are valid, if so only update the plaback indexes
                if self.start_index <= s and s < e and e <= self.end_index and loop_len > self.out_blocksize:
                    self.pb_start_index = ps
                    self.pb_end_index = pe
                    self.loop_size = loop_len
                    self.i = ps
                # If indexes are completely invalid reset sliders back
                elif e <= s or loop_len <= self.out_blocksize:
                    self.start_slider.set((self.pb_start_index / self.stretch_factor + self.start_index) / self.file_len)
                    self.end_slider.set((self.pb_end_index / self.stretch_factor + self.start_index) / self.file_len)
                # If sliders are valid but not in the range of currently computed out_data, we need to recomput
                else:
                    recompute = True
                self.loop_change = False

            # If time or pitch factors change or recomputing is needed
            if self.param_change or recompute:
                # Update internal values
                self.stretch_factor = self.stretch_slider.get()
                self.pitch_factor = self.pitch_slider.get()

                loop_len = int(round((e - s) * self.stretch_factor))

                # Check if indexes are valid
                if s < e and loop_len > self.out_blocksize:

                    # Choose a segment of the original audio padded by 3 seconds on each side
                    self.start_index = max(s -  3 * self.samplerate, 0)
                    self.end_index = min(e + 3 * self.samplerate, self.file_len - 1)

                    # Compute stretched audio
                    self.out_data = self.AP.process(self.start_index, self.end_index,
                                                    self.stretch_factor, self.pitch_factor)

                    # Convert start and end indexes into indexes of the out_data domain and clamp
                    ps = int(round((s - self.start_index) * self.stretch_factor))
                    pe = int(round((e - self.start_index) * self.stretch_factor))

                    ps = max(ps, 0)
                    pe = min(pe, len(self.out_data))

                    # If clamped result is invalid, fall back to full out_data and update playback indexes
                    if pe <= ps:
                        self.pb_start_index = 0
                        self.pb_end_index = len(self.out_data)
                    else:
                        self.pb_start_index = ps
                        self.pb_end_index   = pe

                    self.loop_size = self.pb_end_index - self.pb_start_index
                    self.i = self.pb_start_index

                else:
                    # Reset sliders to a safe position
                    self.start_slider.set((self.pb_start_index / self.stretch_factor + self.start_index) / self.file_len)
                    self.end_slider.set((self.pb_end_index / self.stretch_factor + self.start_index) / self.file_len)

            # Clear flags
            self.param_change = False
            self.loop_change = False

        # Pausing logic
        if not self.is_playing:
            self.pause_button.config(text="Pause")
        else:
            self.pause_button.config(text="Play")

        self.is_playing = not self.is_playing


    def update_start(self, value: float):
        self.loop_change = True
        self.start_label.config(text= "Start: " + self.time_to_string(float(value)))


    def update_end(self, value: float):
        self.loop_change = True
        self.end_label.config(text= "End: " + self.time_to_string(float(value)))


    def update_settings(self, value=None):
        self.param_change = True


    def update_time(self, v):
        self.pb_bar["value"] = 100 * v
        self.time.config(text="Time: " + self.time_to_string(v))


    def time_to_string(self, value: float) -> str:
        """ Converts a value from 0.0 to 1.0 representing a place in the audio segment
        into a string representing its timecode
        returns this computed string"""
        seconds = float(value) * self.file_len / self.samplerate
        milliseconds = int(seconds * 1000 % 1000)
        minutes = int(seconds // 60)
        seconds = int(seconds % 60)

        return f"{minutes:02d}:{seconds:02d}:{milliseconds:03d}"


    def reset_time(self):
        self.stretch_slider.set(1.0)
        self.stretch_factor = 1.0


    def reset_pitch(self):
        self.pitch_slider.set(1.0)
        self.pitch_factor = 1.0


    def rewind(self, value=None):
        self.i = self.pb_start_index

        self.pb_bar["value"] = 100 * (self.start_index + self.pb_start_index) / self.file_len
