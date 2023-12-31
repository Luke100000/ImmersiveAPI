#!/bin/bash

IN=$1
OUT=$2

true ${SD_PARAMS:="-45dB:d=0.2"};
true ${MIN_FRAGMENT_DURATION:="5"};
export MIN_FRAGMENT_DURATION

if [ -z "$OUT" ]; then
    echo "Usage: split_by_silence.sh input_media.mp4 output_template_%03d.mkv"
    echo "Depends on FFmpeg, Bash, Awk, Perl 5. Not tested on Mac or Windows."
    echo ""
    echo "Environment variables (with their current values):"
    echo "    SD_PARAMS=$SD_PARAMS       Parameters for FFmpeg's silencedetect filter: noise tolerance and minimal silence duration"
    echo "    MIN_FRAGMENT_DURATION=$MIN_FRAGMENT_DURATION    Minimal fragment duration"
    exit 1
fi

echo "Determining split points..." >& 2

SPLITS=$(
    ffmpeg  -v warning -i "$IN" -af silencedetect="$SD_PARAMS",ametadata=mode=print:file=-:key=lavfi.silence_start -vn -sn  -f s16le  -y /dev/null \
    | grep lavfi.silence_start= \
    | cut -f 2-2 -d= \
    | perl -ne '
        our $prev;
        INIT { $prev = 0.0; }
        chomp;
        if (($_ - $prev) >= $ENV{MIN_FRAGMENT_DURATION}) {
            print "$_,";
            $prev = $_;
        }
    ' \
    | sed 's!,$!!'
)


echo "Splitting points are $SPLITS"

ffmpeg -v warning -i "$IN" -c copy -map 0 -f segment -segment_times "$SPLITS" "$OUT"
