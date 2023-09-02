import asyncio
import json
import os
import shutil
import time
from collections import defaultdict

from modules.converter.converter import conversions, file_formats
from modules.converter.converters.abc2midi import install_abc2midi

install_abc2midi()
# install_ffmpeg()
# install_imagemagick()
# install_opencv()
# install_pillow()


def get_total_tests():
    total_tests = 0
    for source_format in file_formats:
        for target_format in file_formats:
            converters = conversions[source_format][target_format]
            total_tests += len(converters)
    return total_tests


class Result:
    time: int = 0
    error: str = None
    tested: bool = False

    def __init__(
        self, source_format: str, target_format: str, converter_name: str
    ) -> None:
        super().__init__()

        self.source_format = source_format
        self.target_format = target_format
        self.converter_name = converter_name


async def worker(
    converter, source_path, name, source_format, target_format, converter_name
):
    result = Result(source_format, target_format, converter_name)

    result.tested = True

    try:
        path = "output/" + name

        # Convert
        t = time.time()
        await asyncio.wait_for(
            converter(source_path, path, source_format, target_format), timeout=16
        )
        delta = time.time() - t

        if not os.path.exists(path):
            raise ValueError("No output")

        if os.path.getsize(path) < 1024:
            raise ValueError("Empty output")

        result.time = delta
    except Exception as e:
        print(source_format, target_format, e)
        result.error = str(e)
    return result


async def main():
    # Clear working directory
    shutil.rmtree("output", ignore_errors=True)
    os.makedirs("output", exist_ok=True)

    # Valid entries are conversions which are tested to be working
    valid = {
        "png": "test.png",
        "abc": "test.abc",
        "webm": "test.webm",
        "wav": "test.wav",
    }
    tested = set()

    # Progress
    total_tests = get_total_tests()
    tests_completed = 0

    # Store results
    results = {}
    for source_format in file_formats:
        results[source_format] = {}
        for target_format in file_formats:
            converters = conversions[source_format][target_format].keys()
            results[source_format][target_format] = {
                converter_name: Result(source_format, target_format, converter_name)
                for converter_name in converters
            }

    changes = True
    while changes:
        tasks = []
        changes = False
        for source_format in file_formats:
            for target_format in file_formats:
                converters = conversions[source_format][target_format]
                for converter_name, converter in converters.items():
                    name = f"{source_format}-{converter_name}.{target_format}"

                    if (
                        name not in tested
                        and source_format in valid
                        and len(tasks) < 12
                    ):
                        tested.add(name)
                        changes = True

                        tasks.append(
                            worker(
                                converter,
                                valid[source_format],
                                name,
                                source_format,
                                target_format,
                                converter_name,
                            )
                        )

        for result in await asyncio.gather(*tasks):
            results[result.source_format][result.target_format][
                result.converter_name
            ] = result

            if result.error is None:
                name = f"{result.source_format}-{result.converter_name}.{result.target_format}"
                valid[result.target_format] = "output/" + name

            tests_completed += 1
            print(f"{tests_completed} of {total_tests} completed!")

    # Pick best converter
    best_converters: dict[str, dict[str, str]] = defaultdict(
        lambda: defaultdict(lambda: None)
    )
    for source_format in file_formats:
        for target_format in file_formats:
            for converter_name in conversions[source_format][target_format].keys():
                result = results[source_format][target_format][converter_name]
                existing_name = best_converters[source_format][target_format]
                existing = (
                    result
                    if existing_name is None
                    else results[source_format][target_format][existing_name]
                )
                if (
                    result.tested
                    and result.error is None
                    and result.time <= existing.time
                ):
                    best_converters[source_format][target_format] = converter_name

    # Some stats
    stats_working = 0
    stats_errored = 0
    for source_format in file_formats:
        for target_format in file_formats:
            name = best_converters[source_format][target_format]
            if name is not None:
                result = results[source_format][target_format][name]
                if result.tested:
                    if result.error is not None:
                        stats_working += 1
                    else:
                        stats_errored += 1

    print(
        f"{stats_working} worked, {stats_errored} errored, {total_tests} total, {total_tests - tests_completed} untested"
    )

    with open("results.json", "w") as file:
        json.dump(best_converters, file, indent=2)


if __name__ == "__main__":
    asyncio.run(main())
