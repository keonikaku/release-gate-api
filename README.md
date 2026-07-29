# Release Gate API

A service that decides whether a proposed change may proceed to production, and
a pipeline that will not promote it unless the regression suite passes against
the merged result.

The requirements are in [`docs/requirements.md`](docs/requirements.md). The
service, the suite and the pipeline land next.
