import numpy as np

class AudioProcessor:
    """Class used for storing original audio data and computing time stretched and pitch shifted audio"""
    def __init__(self, data: np.ndarray, samplerate: int, 
                 window_len=4096, hop_len=None, phase_lock = True):
        
        self.samplerate = samplerate
        self.data = data
        self.duration = len(self.data) / self.samplerate

        self.window_len = window_len
        self.hop_len = hop_len
        self.phase_lock = phase_lock
        self.window = np.sqrt(np.hanning(window_len))


    def process(self, start_index: int, end_index: int, stretch_factor: float, pitch_factor: float) -> np.ndarray:
        """Handles processing logic"""
        if start_index >= end_index or start_index >= len(self.data) or end_index >= len(self.data):
            raise ValueError("Invalid index range")

        segment = self.data[start_index : end_index]

        # No processing needed
        if pitch_factor == 1 and stretch_factor == 1:
            return segment.astype(np.float32)
        # Only time stretching is needed
        elif pitch_factor == 1:
            return self.phase_vocoder(segment, stretch_factor)
        
        # Apply all processing
        return self.pitch_shift(segment, stretch_factor, pitch_factor).astype(np.float32)


    def pitch_shift(self, segment: np.ndarray, stretch_factor: float, pitch_factor: float) -> np.ndarray:
        """ Uses the phase vocoder to time stretch the signal by the correct stretch_factor 
        and then resample the signal to speed up or slow down the signal - resulting in pitch shifting

        Returns an audio array of a pitch shifted signal.
        """

        stretched = self.phase_vocoder(segment, stretch_factor * pitch_factor)
        new_length = int(len(segment) * stretch_factor)
        return self.resample(stretched, new_length).astype(np.float32)
        

    def phase_vocoder(self, segment: np.ndarray, stretch_factor: float) -> np.ndarray:
        
        """Time-stretches an audio signal by a given stretch_factor
        by splitting it into overlapping blocks of length window_len,
        spaced by an analysis hop size hop_a.

        For each of these blocks, the function takes a Short-Time Fourier Transform (STFT) of the signal
        and uses the information to reconstruct a different block of audio with the same frequencies.
        
        These reconstructed blocks are added to the resulting signal but they are spaced
        by hop_s so the resulting audio signal is time stretched. The frequencies are unchanged so
        the pitch information is the same. Because the blocks start at different times, phases of each frequency 
        have to be computed so that the result sounds cohesive and not robotic.

        Larger window_len sizes provide better tonal information but worse rhythmic information while
        Smaller window_len sizes provide better rhythmic information but worse tonal information

        Returns an array of the time stretch audio signal.
        """

        if not self.hop_len:
            # If not specified by a user, hop_a is set so the blocks overlap by 75 %
            # which provides good sound quality while not being too expensive for processing
            hop_a = int(self.window_len // 4)
        else:
            hop_a = self.hop_len

        # Initialise hop length for synthesis
        hop_s = int(round(stretch_factor * hop_a))

        num_frames = (len(segment) - self.window_len) // hop_a + 1
        output_len = int(num_frames * hop_s) + self.window_len
        result = np.zeros(output_len)

        # Array of phases from previous frames
        previous_phase = np.zeros(self.window_len // 2 + 1)

        # Array of expected phase advances for each bin over a time frame of length hop_a
        expected_phase_advance = 2 * np.pi * np.arange(self.window_len // 2 + 1) / self.window_len * hop_a
        
        previous_phase_synthesis = np.zeros(self.window_len // 2 + 1)
        
        # Energy in decibels used to detect transients
        energy_previous_db = 0
        is_transient = False

        # Go over each block of audio of length window_len each hop_a apart
        for n in range(num_frames):
            i = n * hop_a
            current_block = segment[i: i + self.window_len] * self.window
            
            # Takes a Fourier Transform of a signal block
            # X is an array containing complex numbers
            # Each array corresponds to a frequency: k-th index corresponds to (k / window_len) * sampling rate
            # Summing all these frequencies with correct amplitude and phase produces the original block (approximately)
            # Magnitude of k-th complex numbers is the amplitude of the k-th frequency
            # The phase of the k-th frequency is given by the angle of k-th complex number
            # For real valued inputs, X[k] is equal to the complex conjugate of X[N-k],
            # so only a half of the bins are needed -> X has the length of (window_len // 2 + 1)
            X = np.fft.rfft(current_block)

            mag = np.abs(X)
            current_phase = np.angle(X)

            # Transient frames will be processed as the new starting frame
            is_transient, energy_previous_db = self.detect_transient(current_block, energy_previous_db)

            # Initialise the first frame by copying all the information 
            # If a frame is a transient, treat it as a new frame to avoid audio smearing
            if n == 0 or is_transient:
                output_angle = current_phase.copy()
                previous_phase = current_phase.copy()
                previous_phase_synthesis = current_phase.copy()
            else:
                actual_phase_advance = (current_phase - previous_phase)
                # Phase unwrapping
                phase_difference = actual_phase_advance - expected_phase_advance
                phase_difference = (phase_difference + np.pi) % (2 * np.pi) - np.pi

                # The bin frequency doesnt have to be the exact frequency in the signal
                # With the measured phase deviation we can find the actual frequency
                actual_phase = expected_phase_advance + phase_difference
                actual_frequency = actual_phase / hop_a
                
                previous_phase = current_phase.copy()

                # Compute the correct phases for signal synthesis
                if not self.phase_lock:
                    output_angle = previous_phase_synthesis + actual_frequency * hop_s

                # Energy can sometimes leak to neighbouring bins.
                # For phase coherence accross neighbouring bins, we find the peaks in the spectrum
                # and use their phases for the adjacent bins to improve sound quality
                else:
                    output_angle = np.zeros(len(previous_phase_synthesis))
                    
                    # Find peak indices and regions of neighbouring bins
                    peaks, regions = self.locate_peaks(mag)
                    if len(peaks) == 0: peaks = [1]

                    # Update each region and peak bin 
                    for j in range(len(peaks) - 1):
                        peak = peaks[j]
                        region = regions[j]
                        output_angle[region] = previous_phase_synthesis[peak] + actual_frequency[peak] * hop_s + (current_phase[region]- current_phase[peak])
                        output_angle[peak] = previous_phase_synthesis[peak] + actual_frequency[peak] * hop_s        

                    # update last peak region
                    peak = peaks[-1]
                    region = regions[-1]
                    output_angle[region] = previous_phase_synthesis[peak] + actual_frequency[peak] * hop_s + (current_phase[region]- current_phase[peak])
                    output_angle[peak] = previous_phase_synthesis[peak] + actual_frequency[peak] * hop_s

            # Calculate the starting index of the reconstructed audio block
            i2 = int(n * hop_s)
            
            previous_phase_synthesis = output_angle
            
            # Synthesise back the output with the same amplitudes, but new computed phases
            # Use inverse FFT to get the signal in the time domain
            Y = mag * np.exp(1j * output_angle)
            output = np.fft.irfft(Y).real

            # Fade edges of the block using a windowing function and add to the result
            result[i2: i2 + self.window_len] += output * self.window

        # Normalise the result
        m = np.max(np.abs(result))
        if m != 0:
            result = result / m

        # Trim or pad the result based on expected length
        target_len = int(len(segment) * stretch_factor)

        if len(result) < target_len:
            # Pad with zeros at the end
            result = np.pad(result, (0, target_len - len(result)))
        else:
            # trim extra samples
            result = result[:target_len]
        
        return result[:]


    def resample(self, input: np.ndarray, new_len: int) -> np.ndarray:
        """Implements linear resampling"""
        old_len = len(input)

        new_indices = np.linspace(0, old_len - 1, new_len)

        left = np.floor(new_indices).astype(int)
        right = np.minimum(left + 1, old_len - 1)
        
        f = new_indices - left
        
        return (1 - f) * input[left] + f * input[right]


    def locate_peaks(self, magnitudes: list, rel_threshold=0.03, neighbours=4) -> tuple:
        """ Finds indices of peaks in an array of magnitudes
        if a value is larger than the threshold and is also the largest among its 4
        neighbours, it is considered as a peak
        
        Returns a tuple of 2 lists
        first list is a list of peak indices
        second is a list of all regions nearest to the respective peak index
        """

        threshold = rel_threshold * magnitudes.max()
        peaks = []
        index = neighbours
        regions = []
        last_peak = -1
        start_point = 0
        end_point = 0

        # Find peaks and regions
        while index < len(magnitudes) - neighbours:
            local_max = np.amax(magnitudes[index - neighbours:index + neighbours + 1])
            if local_max < threshold:
                index += neighbours
            elif magnitudes[index] == local_max:
                peaks.append(index)
                # If we have a first peak
                if last_peak == -1:
                    last_peak = index
                else:
                    end_point = (last_peak + index) // 2
                    regions.append(list(range(start_point, last_peak)) + list(range(last_peak + 1, end_point)))
                    start_point = end_point
                    last_peak = index
            index += 1

        # Cover region of the last peak
        regions.append(list(range(start_point, last_peak)) + list(range(last_peak + 1, len(magnitudes))))

        return (peaks, regions)
    

    def detect_transient(self, audio_block: np.ndarray, energy_previous_db: float, threshold_db=6.0) -> bool:
        """ A transient is a sudden high energy event in a signal.
        They are often caused by drums or attack portions of sounds.

        Detects transient frames and updates energy_previous_db for the next frame 
        """
        # Energy here is similar to acoustic energy but the array of magnitudes is normalised so it
        # is not in any unit just the squares of magnitudes
        energy_current = np.sum(np.square((audio_block) * self.window))
        # Prevent log of zero
        if energy_current <= 1e-12:
            energy_current_db = -120.0
        # Convert to decibels
        else:
            energy_current_db = 10 * np.log10(energy_current)

        if energy_current_db - energy_previous_db > threshold_db:
            return (True, energy_current_db)
        

        return (False, energy_current_db)
