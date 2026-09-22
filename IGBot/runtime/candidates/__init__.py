"""Candidate discovery framework for interaction modules."""

from IGBot.runtime.candidates.contracts import (
    CandidateFilter,
    CandidateProfileReader,
    CandidateProvider,
    FollowersDiscovery,
    SpecificAccountDiscovery,
)
from IGBot.runtime.candidates.models import (
    Candidate,
    CandidateObservation,
    CandidateProviderType,
    CandidateResult,
    CandidateResultStatus,
    DiscoveryResult,
    DiscoveryStatus,
    FollowersDiscoverySettings,
)
from IGBot.runtime.candidates.providers import (
    FollowersProvider,
    SpecificAccountsProvider,
    SpecificUsersProvider,
)
from IGBot.runtime.candidates.qualifier import CandidateQualifier

__all__ = [
    "Candidate",
    "CandidateFilter",
    "CandidateObservation",
    "CandidateProfileReader",
    "CandidateProvider",
    "CandidateProviderType",
    "CandidateQualifier",
    "CandidateResult",
    "CandidateResultStatus",
    "DiscoveryResult",
    "DiscoveryStatus",
    "FollowersDiscovery",
    "FollowersDiscoverySettings",
    "FollowersProvider",
    "SpecificAccountDiscovery",
    "SpecificAccountsProvider",
    "SpecificUsersProvider",
]
