from setuptools import setup

setup(
    name='mpvinfod',
    version='0.1',
    py_modules=['mpvinfod'],
    entry_points={
        'console_scripts': ['mpvinfod = mpvinfod:run']
    },
)
