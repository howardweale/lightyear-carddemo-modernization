"""CI-only Java 21 parser probe using a disposable public fixture in the job workspace."""
from pathlib import Path
import subprocess
import tempfile

from tools.intcalc_stage2_memory_route import template


def main():
    src = """public class Main {
        public static void main(String[] args) {
            for (String arg : args) System.out.println(arg);
        }
    }"""
    with tempfile.TemporaryDirectory() as scratch:
        root = Path(scratch)
        (root / "Main.java").write_text(src, encoding="ascii")
        subprocess.run(["javac","--release","21","Main.java"], cwd=root, check=True)
        subprocess.run(["jar","--create","--file","public.jar","--main-class","Main","Main.class"],
                       cwd=root, check=True)
        for date,stamp in [("2026112000","2026-11-20-11.22.33.440000"),
                           ("2000022900","2000-02-29-00.00.00.000000")]:
            args = template(date,stamp)
            # Only the fixture jar location is relative in this host parser probe.
            # The Docker-boundary test separately compares the complete absolute command.
            args[2] = "public.jar"
            (root/"case-clock.args").write_bytes(("\n".join(args)+"\n").encode("ascii"))
            actual = subprocess.run(["java","@case-clock.args"],cwd=root,capture_output=True,check=True)
            if actual.stdout != ("\n".join(args[3:])+"\n").encode("ascii") or actual.stderr:
                raise SystemExit("public-java-argument-probe")
        print("public-java-argument-probe: two argument vectors matched")


if __name__=="__main__":
    main()
