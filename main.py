"""
LoRA Data Toolkit - Main Entry Point
A simple tool to collect, organize, and export training data for LoRA fine-tuning.
"""
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gui.app import App


def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
