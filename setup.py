from setuptools import setup

setup(
    name='mpvinfo',
    version='0.1',
    py_modules=['mpvinfo'],
    entry_points={
        'console_scripts': ['mpvinfo = mpvinfo:run']
    },
)
