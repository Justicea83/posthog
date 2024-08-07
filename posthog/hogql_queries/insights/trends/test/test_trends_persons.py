from typing import Optional, Union
from unittest.case import skip

from django.test import override_settings
from django.utils import timezone
from freezegun import freeze_time
import pytest

from posthog.api.test.test_team import create_team
from posthog.hogql_queries.actors_query_runner import ActorsQueryRunner
from posthog.hogql_queries.insights.trends.breakdown import BREAKDOWN_NULL_STRING_LABEL
from posthog.models import Team, Cohort, GroupTypeMapping
from posthog.models.group.util import create_group
from posthog.models.property_definition import PropertyDefinition, PropertyType
from posthog.schema import (
    ActorsQuery,
    BaseMathType,
    Breakdown,
    BreakdownFilter,
    BreakdownType,
    ChartDisplayType,
    Compare,
    CountPerActorMathType,
    InsightDateRange,
    EventsNode,
    InsightActorsQuery,
    MathGroupTypeIndex,
    PropertyMathType,
    TrendsFilter,
    TrendsQuery,
    CompareFilter,
    HogQLQueryModifiers,
)
from posthog.test.base import (
    APIBaseTest,
    ClickhouseTestMixin,
    _create_event,
    _create_person,
)


def get_actors(
    trends_query: TrendsQuery,
    team: Team,
    breakdown: Optional[Union[str, int]] = None,
    compare: Optional[Compare] = None,
    day: Optional[Union[str, int]] = None,
    interval: Optional[int] = None,
    series: Optional[int] = None,
    status: Optional[str] = None,
    offset: Optional[int] = None,
    includeRecordings: Optional[bool] = None,
):
    insight_actors_query = InsightActorsQuery(
        source=trends_query,
        breakdown=breakdown,
        compare=compare,
        day=day,
        interval=interval,
        series=series,
        status=status,
        includeRecordings=includeRecordings,
        modifiers=trends_query.modifiers,
    )
    actors_query = ActorsQuery(
        source=insight_actors_query,
        offset=offset,
        select=[
            "actor",
            "created_at",
            "event_count",
            *(["matched_recordings"] if includeRecordings else []),
        ],
        orderBy=["event_count DESC"],
        modifiers=trends_query.modifiers,
    )
    response = ActorsQueryRunner(query=actors_query, team=team).calculate()
    return response.results


def _create_cohort(**kwargs):
    team = kwargs.pop("team")
    name = kwargs.pop("name")
    groups = kwargs.pop("groups")
    cohort = Cohort.objects.create(team=team, name=name, groups=groups, last_calculation=timezone.now())
    cohort.calculate_people_ch(pending_version=0)
    return cohort


def get_distinct_id(result):
    return result[0]["distinct_ids"][0]


def get_group_name(result):
    return result[0]["id"]


def get_event_count(result):
    return result[2]


@override_settings(IN_UNIT_TESTING=True)
class TestTrendsPersons(ClickhouseTestMixin, APIBaseTest):
    maxDiff = None

    def _get_actors(self, trends_query: TrendsQuery, **kwargs):
        return get_actors(trends_query=trends_query, team=self.team, **kwargs, includeRecordings=True)

    def _create_events(self):
        _create_person(
            team_id=self.team.pk,
            distinct_ids=["person1"],
            properties={"$geoip_country_code": "US"},
        )
        _create_person(
            team_id=self.team.pk,
            distinct_ids=["person2"],
            properties={"$geoip_country_code": "DE"},
        )
        _create_person(
            team_id=self.team.pk,
            distinct_ids=["person3"],
            properties={"$geoip_country_code": "DE"},
        )

        _create_event(
            event="$pageview",
            distinct_id="person1",
            timestamp="2023-04-29 16:00",
            properties={"$browser": "Chrome"},
            team=self.team,
        )
        _create_event(
            event="$pageleave",
            distinct_id="person1",
            timestamp="2023-04-29 17:00",
            properties={"$browser": "Chrome"},
            team=self.team,
        )
        _create_event(
            event="$pageview",
            distinct_id="person2",
            timestamp="2023-04-29 17:00",
            properties={"$browser": "Safari"},
            team=self.team,
        )
        _create_event(
            event="$pageview",
            distinct_id="person2",
            timestamp="2023-04-29 18:00",
            properties={"$browser": "Safari"},
            team=self.team,
        )

        _create_event(
            event="$pageview",
            distinct_id="person1",
            timestamp="2023-05-01 16:00",
            properties={"$browser": "Chrome", "some_property": 20},
            team=self.team,
        )
        _create_event(
            event="$pageview",
            distinct_id="person1",
            timestamp="2023-05-01 17:00",
            properties={"$browser": "Chrome"},
            team=self.team,
        )
        _create_event(
            event="$pageview",
            distinct_id="person1",
            timestamp="2023-05-01 18:00",
            properties={"$browser": "Chrome"},
            team=self.team,
        )
        _create_event(
            event="$pageview",
            distinct_id="person2",
            timestamp="2023-05-01 16:00",
            properties={"$browser": "Safari", "some_property": 22},
            team=self.team,
        )
        _create_event(
            event="$pageview",
            distinct_id="person2",
            timestamp="2023-05-01 17:00",
            properties={"$browser": "Safari"},
            team=self.team,
        )
        _create_event(
            event="$pageview",
            distinct_id="person3",
            timestamp="2023-05-01 16:00",
            properties={"$browser": "Safari"},
            team=self.team,
        )

        _create_event(
            event="$pageview",
            distinct_id="person1",
            timestamp="2023-05-06 16:00",
            properties={"some_property": 20},
            team=self.team,
        )

        other_team = create_team(self.team.organization)

        _create_person(
            team_id=other_team.pk,
            distinct_ids=["person4"],
            properties={"$geoip_country_code": "US"},
        )

        for i in range(6):
            _create_event(
                event="$pageview",
                distinct_id="person4",
                timestamp=f"2023-04-{30-i} 16:00",
                properties={"some_property": 20},
                team=other_team,
            )
            _create_event(
                event="$pageview",
                distinct_id="person4",
                timestamp=f"2023-05-0{i+1} 16:00",
                properties={"some_property": 20},
                team=other_team,
            )

    def _create_numeric_events(self):
        _create_person(
            team_id=self.team.pk,
            distinct_ids=["person1"],
            properties={"$geoip_country_code": "US"},
        )
        _create_person(
            team_id=self.team.pk,
            distinct_ids=["person2"],
            properties={"$geoip_country_code": "DE"},
        )
        _create_person(
            team_id=self.team.pk,
            distinct_ids=["person3"],
            properties={"$geoip_country_code": "DE"},
        )

        _create_event(
            event="$pageview",
            distinct_id="person1",
            timestamp="2023-04-29 16:00",
            properties={"some_property": 20},
            team=self.team,
        )
        _create_event(
            event="$pageview",
            distinct_id="person2",
            timestamp="2023-04-29 17:00",
            properties={"some_property": 60},
            team=self.team,
        )
        _create_event(
            event="$pageview",
            distinct_id="person1",
            timestamp="2023-05-01 16:00",
            properties={"some_property": 40},
            team=self.team,
        )
        _create_event(
            event="$pageview",
            distinct_id="person1",
            timestamp="2023-05-01 18:00",
            properties={"some_property": 0},
            team=self.team,
        )
        _create_event(
            event="$pageview",
            distinct_id="person2",
            timestamp="2023-05-01 17:00",
            properties={"some_property": 80},
            team=self.team,
        )
        _create_event(
            event="$pageview",
            distinct_id="person3",
            timestamp="2023-05-01 16:00",
            properties={"$browser": "Safari"},
            team=self.team,
        )
        _create_event(
            event="$pageview",
            distinct_id="person1",
            timestamp="2023-05-06 16:00",
            properties={"some_property": 20},
            team=self.team,
        )
        PropertyDefinition.objects.create(team=self.team, name="some_property", property_type=PropertyType.Numeric)

    def test_trends_single_series_persons(self):
        self._create_events()
        source_query = TrendsQuery(
            series=[EventsNode(event="$pageview")],
            dateRange=InsightDateRange(date_from="-7d"),
        )

        result = self._get_actors(trends_query=source_query, day="2023-04-29")

        self.assertEqual(get_distinct_id(result[0]), "person2")
        self.assertEqual(get_event_count(result[0]), 2)
        self.assertEqual(get_distinct_id(result[1]), "person1")
        self.assertEqual(get_event_count(result[1]), 1)

    def test_trends_multiple_series_persons(self):
        self._create_events()
        source_query = TrendsQuery(
            series=[EventsNode(event="$pageview"), EventsNode(event="$pageleave")],
            dateRange=InsightDateRange(date_from="-7d"),
        )

        result = self._get_actors(trends_query=source_query, day="2023-04-29")

        self.assertEqual(len(result), 2)
        self.assertEqual(get_distinct_id(result[0]), "person2")
        self.assertEqual(get_event_count(result[0]), 2)
        self.assertEqual(get_distinct_id(result[1]), "person1")
        self.assertEqual(get_event_count(result[1]), 1)

        result = self._get_actors(trends_query=source_query, day="2023-04-29", series=1)

        self.assertEqual(len(result), 1)
        self.assertEqual(get_distinct_id(result[0]), "person1")
        self.assertEqual(get_event_count(result[0]), 1)

    def test_trends_event_breakdown_persons(self):
        self._create_events()
        source_query = TrendsQuery(
            series=[EventsNode(event="$pageview")],
            dateRange=InsightDateRange(date_from="-7d"),
            breakdownFilter=BreakdownFilter(breakdown="$browser"),
        )

        result = self._get_actors(trends_query=source_query, day="2023-05-01", breakdown="Safari")

        self.assertEqual(len(result), 2)
        self.assertEqual(get_distinct_id(result[0]), "person2")
        self.assertEqual(get_event_count(result[0]), 2)
        self.assertEqual(get_distinct_id(result[1]), "person3")
        self.assertEqual(get_event_count(result[1]), 1)

        result = self._get_actors(trends_query=source_query, day="2023-05-01", breakdown="Firefox")

        self.assertEqual(len(result), 0)

    def test_trends_person_breakdown_persons(self):
        self._create_events()
        source_query = TrendsQuery(
            series=[EventsNode(event="$pageview")],
            dateRange=InsightDateRange(date_from="-7d"),
            breakdownFilter=BreakdownFilter(breakdown="$geoip_country_code", breakdown_type=BreakdownType.PERSON),
        )

        result = self._get_actors(trends_query=source_query, day="2023-05-01", breakdown="DE")

        self.assertEqual(len(result), 2)
        self.assertEqual(get_distinct_id(result[0]), "person2")
        self.assertEqual(get_event_count(result[0]), 2)
        self.assertEqual(get_distinct_id(result[1]), "person3")
        self.assertEqual(get_event_count(result[1]), 1)

        result = self._get_actors(trends_query=source_query, day="2023-05-01", breakdown="UK")

        self.assertEqual(len(result), 0)

    @skip("fails, as other returns all breakdowns, even those that should be display with the breakdown_limit")
    def test_trends_breakdown_others_persons(self):
        self._create_events()
        source_query = TrendsQuery(
            series=[EventsNode(event="$pageview")],
            dateRange=InsightDateRange(date_from="-7d"),
            breakdownFilter=BreakdownFilter(breakdown="$browser", breakdown_limit=1),
        )

        result = self._get_actors(trends_query=source_query, day="2023-04-29", breakdown="Chrome")

        self.assertEqual(len(result), 1)
        self.assertEqual(get_distinct_id(result[0]), "person1")
        self.assertEqual(get_event_count(result[0]), 2)

        result = self._get_actors(
            trends_query=source_query, day="2023-04-29", breakdown="$$_posthog_breakdown_other_$$"
        )

        self.assertEqual(len(result), 1)
        self.assertEqual(get_distinct_id(result[0]), "person2")
        self.assertEqual(get_event_count(result[0]), 2)

    def test_trends_breakdown_null_persons(self):
        self._create_events()
        source_query = TrendsQuery(
            series=[EventsNode(event="$pageview")],
            dateRange=InsightDateRange(date_from="-7d"),
            breakdownFilter=BreakdownFilter(breakdown="$browser", breakdown_limit=1),
        )

        result = self._get_actors(trends_query=source_query, day="2023-05-06", breakdown="Chrome")

        self.assertEqual(len(result), 0)

        result = self._get_actors(trends_query=source_query, day="2023-05-06", breakdown="$$_posthog_breakdown_null_$$")

        self.assertEqual(len(result), 1)
        self.assertEqual(get_distinct_id(result[0]), "person1")
        self.assertEqual(get_event_count(result[0]), 1)

    def test_trends_breakdown_hogql_persons(self):
        self._create_events()
        source_query = TrendsQuery(
            series=[EventsNode(event="$pageview")],
            dateRange=InsightDateRange(date_from="-7d"),
            breakdownFilter=BreakdownFilter(breakdown="properties.some_property", breakdown_type=BreakdownType.HOGQL),
        )

        result = self._get_actors(trends_query=source_query, day="2023-05-01", breakdown=20)
        self.assertEqual(len(result), 1)
        self.assertEqual(get_distinct_id(result[0]), "person1")
        self.assertEqual(get_event_count(result[0]), 1)

        result = self._get_actors(trends_query=source_query, day="2023-05-01", breakdown=10)

        self.assertEqual(len(result), 0)

    def test_trends_cohort_breakdown_persons(self):
        self._create_events()
        cohort = _create_cohort(
            team=self.team,
            name="DE users",
            groups=[{"properties": [{"key": "$geoip_country_code", "value": "DE", "type": "person"}]}],
        )
        source_query = TrendsQuery(
            series=[EventsNode(event="$pageview")],
            dateRange=InsightDateRange(date_from="-7d"),
            breakdownFilter=BreakdownFilter(breakdown=[cohort.pk], breakdown_type=BreakdownType.COHORT),
        )

        result = self._get_actors(trends_query=source_query, day="2023-05-01", breakdown=cohort.pk)

        self.assertEqual(len(result), 2)
        self.assertEqual(get_distinct_id(result[0]), "person2")
        self.assertEqual(get_event_count(result[0]), 2)
        self.assertEqual(get_distinct_id(result[1]), "person3")
        self.assertEqual(get_event_count(result[1]), 1)

    def test_trends_multi_cohort_breakdown_persons(self):
        self._create_events()
        cohort1 = _create_cohort(
            team=self.team,
            name="US users",
            groups=[{"properties": [{"key": "$geoip_country_code", "value": "US", "type": "person"}]}],
        )
        cohort2 = _create_cohort(
            team=self.team,
            name="DE users",
            groups=[{"properties": [{"key": "$geoip_country_code", "value": "DE", "type": "person"}]}],
        )
        source_query = TrendsQuery(
            series=[EventsNode(event="$pageview")],
            dateRange=InsightDateRange(date_from="-7d"),
            breakdownFilter=BreakdownFilter(breakdown=[cohort1.pk, cohort2.pk], breakdown_type=BreakdownType.COHORT),
        )

        result = self._get_actors(trends_query=source_query, day="2023-05-01", breakdown=cohort1.pk)

        self.assertEqual(len(result), 1)
        self.assertEqual(get_distinct_id(result[0]), "person1")
        self.assertEqual(get_event_count(result[0]), 3)

        result = self._get_actors(trends_query=source_query, day="2023-05-01", breakdown=cohort2.pk)

        self.assertEqual(len(result), 2)
        self.assertEqual(get_distinct_id(result[0]), "person2")
        self.assertEqual(get_event_count(result[0]), 2)
        self.assertEqual(get_distinct_id(result[1]), "person3")
        self.assertEqual(get_event_count(result[1]), 1)

    def trends_all_cohort_breakdown_persons(self, inCohortVia: str):
        self._create_events()
        cohort1 = _create_cohort(
            team=self.team,
            name="US users",
            groups=[{"properties": [{"key": "$geoip_country_code", "value": "US", "type": "person"}]}],
        )
        source_query = TrendsQuery(
            series=[EventsNode(event="$pageview")],
            dateRange=InsightDateRange(date_from="-7d"),
            breakdownFilter=BreakdownFilter(breakdown=[cohort1.pk, "all"], breakdown_type=BreakdownType.COHORT),
        )

        source_query.modifiers = HogQLQueryModifiers(inCohortVia=inCohortVia)

        result = self._get_actors(trends_query=source_query, day="2023-05-01", breakdown=cohort1.pk)

        self.assertEqual(len(result), 1)
        self.assertEqual(get_distinct_id(result[0]), "person1")
        self.assertEqual(get_event_count(result[0]), 3)

        result = self._get_actors(trends_query=source_query, day="2023-05-01", breakdown="all")

        self.assertEqual(len(result), 3)
        self.assertEqual(get_distinct_id(result[0]), "person1")
        self.assertEqual(get_event_count(result[0]), 3)
        self.assertEqual(get_distinct_id(result[1]), "person2")
        self.assertEqual(get_event_count(result[1]), 2)
        self.assertEqual(get_distinct_id(result[2]), "person3")
        self.assertEqual(get_event_count(result[2]), 1)

    def test_trends_all_cohort_breakdown_persons_subquery(self):
        self.trends_all_cohort_breakdown_persons("subquery")

    def test_trends_all_cohort_breakdown_persons_leftjoin(self):
        self.trends_all_cohort_breakdown_persons("leftjoin")

    def test_trends_all_cohort_breakdown_persons_leftjoin_conjoined(self):
        self.trends_all_cohort_breakdown_persons("leftjoin_conjoined")

    def test_trends_math_weekly_active_persons(self):
        for i in range(17, 24):
            distinct_id = f"person_2023-04-{i}"
            _create_person(
                team_id=self.team.pk,
                distinct_ids=[distinct_id],
            )
            _create_event(
                event="$pageview",
                distinct_id=distinct_id,
                timestamp=f"2023-04-{i} 16:00",
                team=self.team,
            )
        source_query = TrendsQuery(
            series=[EventsNode(event="$pageview", math=BaseMathType.WEEKLY_ACTIVE)],
            dateRange=InsightDateRange(date_from="-7d"),
        )

        result = self._get_actors(trends_query=source_query, day="2023-04-28")

        self.assertEqual(len(result), 2)
        self.assertEqual(
            {get_distinct_id(result[0]), get_distinct_id(result[1])}, {"person_2023-04-22", "person_2023-04-23"}
        )

    @skip("fails, as event_count isn't populated properly")
    def test_trends_math_property_sum_persons(self):
        self._create_events()
        source_query = TrendsQuery(
            series=[EventsNode(event="$pageview", math=PropertyMathType.SUM, math_property="some_property")],
            dateRange=InsightDateRange(date_from="-7d"),
        )

        result = self._get_actors(trends_query=source_query, day="2023-05-01")

        self.assertEqual(len(result), 3)
        self.assertEqual(get_distinct_id(result[0]), "person2")
        self.assertEqual(get_event_count(result[0]), 22)
        self.assertEqual(get_distinct_id(result[1]), "person1")
        self.assertEqual(get_event_count(result[1]), 20)
        self.assertEqual(get_distinct_id(result[2]), "person3")
        self.assertEqual(get_event_count(result[2]), 0)

    @skip("fails, as event_count isn't populated properly")
    def test_trends_math_count_per_actor_persons(self):
        self._create_events()
        source_query = TrendsQuery(
            series=[
                EventsNode(
                    event="$pageview", math=CountPerActorMathType.MAX_COUNT_PER_ACTOR, math_property="some_property"
                )
            ],
            dateRange=InsightDateRange(date_from="-7d"),
        )

        result = self._get_actors(trends_query=source_query, day="2023-05-01")

        self.assertEqual(len(result), 3)
        self.assertEqual(get_distinct_id(result[0]), "person2")
        self.assertEqual(get_event_count(result[0]), 22)
        self.assertEqual(get_distinct_id(result[1]), "person1")
        self.assertEqual(get_event_count(result[1]), 20)
        self.assertEqual(get_distinct_id(result[2]), "person3")
        self.assertEqual(get_event_count(result[2]), 0)

    def test_trends_math_group_persons(self):
        GroupTypeMapping.objects.create(team=self.team, group_type="Company", group_type_index=0)
        create_group(team_id=self.team.pk, group_type_index=0, group_key="Hooli")
        create_group(team_id=self.team.pk, group_type_index=0, group_key="Pied Piper")

        _create_event(
            event="$pageview",
            distinct_id="person1",
            timestamp="2023-05-01 16:00",
            properties={"$group_0": "Hooli"},
            team=self.team,
        )
        _create_event(
            event="$pageview",
            distinct_id="person1",
            timestamp="2023-05-01 17:00",
            properties={"$group_0": "Hooli"},
            team=self.team,
        )
        _create_event(
            event="$pageview",
            distinct_id="person1",
            timestamp="2023-05-01 18:00",
            properties={"$group_0": "Pied Piper"},
            team=self.team,
        )
        source_query = TrendsQuery(
            series=[
                EventsNode(event="$pageview", math="unique_group", math_group_type_index=MathGroupTypeIndex.NUMBER_0)
            ],
            dateRange=InsightDateRange(date_from="-7d"),
        )

        result = self._get_actors(trends_query=source_query, day="2023-05-01")

        self.assertEqual(len(result), 2)
        self.assertEqual(get_group_name(result[0]), "Hooli")
        self.assertEqual(get_event_count(result[0]), 2)
        self.assertEqual(get_group_name(result[1]), "Pied Piper")
        self.assertEqual(get_event_count(result[1]), 1)

    def test_trends_math_group_persons_filters_empty(self):
        GroupTypeMapping.objects.create(team=self.team, group_type="Company", group_type_index=0)
        create_group(team_id=self.team.pk, group_type_index=0, group_key="Hooli")
        create_group(team_id=self.team.pk, group_type_index=0, group_key="")

        _create_event(
            event="$pageview",
            distinct_id="person1",
            timestamp="2023-05-01 16:00",
            properties={"$group_0": "Hooli"},
            team=self.team,
        )
        _create_event(
            event="$pageview",
            distinct_id="person1",
            timestamp="2023-05-01 17:00",
            team=self.team,
        )
        source_query = TrendsQuery(
            series=[
                EventsNode(event="$pageview", math="unique_group", math_group_type_index=MathGroupTypeIndex.NUMBER_0)
            ],
            dateRange=InsightDateRange(date_from="-7d"),
        )

        result = self._get_actors(trends_query=source_query, day="2023-05-01")

        self.assertEqual(len(result), 1)
        self.assertEqual(get_group_name(result[0]), "Hooli")
        self.assertEqual(get_event_count(result[0]), 1)

    def test_trends_total_value_persons(self):
        self._create_events()
        source_query = TrendsQuery(
            series=[EventsNode(event="$pageview")],
            dateRange=InsightDateRange(date_from="-7d"),
            trendsFilter=TrendsFilter(display=ChartDisplayType.BOLD_NUMBER),
        )

        with freeze_time("2023-05-01T20:00:00.000Z"):
            # note: total value actors should be called without day
            result = self._get_actors(trends_query=source_query)

        self.assertEqual(len(result), 3)
        self.assertEqual(get_event_count(result[0]), 4)
        self.assertEqual(get_event_count(result[1]), 4)
        self.assertEqual(get_distinct_id(result[2]), "person3")
        self.assertEqual(get_event_count(result[2]), 1)

    def test_trends_compare_persons(self):
        self._create_events()
        source_query = TrendsQuery(
            series=[EventsNode(event="$pageview")],
            dateRange=InsightDateRange(date_from="-7d"),
            trendsFilter=TrendsFilter(),
            compareFilter=CompareFilter(compare=True),
        )

        result = self._get_actors(trends_query=source_query, day="2023-05-06", compare=Compare.CURRENT)

        self.assertEqual(len(result), 1)
        self.assertEqual(get_distinct_id(result[0]), "person1")
        self.assertEqual(get_event_count(result[0]), 1)

        result = self._get_actors(trends_query=source_query, day="2023-05-06", compare=Compare.PREVIOUS)

        self.assertEqual(len(result), 2)
        self.assertEqual(get_distinct_id(result[0]), "person2")
        self.assertEqual(get_event_count(result[0]), 2)
        self.assertEqual(get_distinct_id(result[1]), "person1")
        self.assertEqual(get_event_count(result[1]), 1)

    def test_trends_event_multiple_breakdowns_persons(self):
        self._create_events()
        source_query = TrendsQuery(
            series=[EventsNode(event="$pageview")],
            dateRange=InsightDateRange(date_from="-7d"),
            breakdownFilter=BreakdownFilter(breakdowns=[Breakdown(value="$browser")]),
        )

        result = self._get_actors(trends_query=source_query, day="2023-05-01", breakdown=["Safari"])

        self.assertEqual(len(result), 2)
        self.assertEqual(get_distinct_id(result[0]), "person2")
        self.assertEqual(get_event_count(result[0]), 2)
        self.assertEqual(get_distinct_id(result[1]), "person3")
        self.assertEqual(get_event_count(result[1]), 1)

        result = self._get_actors(trends_query=source_query, day="2023-05-01", breakdown=["Firefox"])

        self.assertEqual(len(result), 0)

    def test_trends_person_multiple_breakdown_persons(self):
        self._create_events()
        source_query = TrendsQuery(
            series=[EventsNode(event="$pageview")],
            dateRange=InsightDateRange(date_from="-7d"),
            breakdownFilter=BreakdownFilter(
                breakdowns=[Breakdown(value="$geoip_country_code", type=BreakdownType.PERSON)]
            ),
        )

        result = self._get_actors(trends_query=source_query, day="2023-05-01", breakdown=["DE"])

        self.assertEqual(len(result), 2)
        self.assertEqual(get_distinct_id(result[0]), "person2")
        self.assertEqual(get_event_count(result[0]), 2)
        self.assertEqual(get_distinct_id(result[1]), "person3")
        self.assertEqual(get_event_count(result[1]), 1)

        result = self._get_actors(trends_query=source_query, day="2023-05-01", breakdown=["UK"])

        self.assertEqual(len(result), 0)

    @skip("fails, as other returns all breakdowns, even those that should be display with the breakdown_limit")
    def test_trends_multiple_breakdowns_others_persons(self):
        self._create_events()
        source_query = TrendsQuery(
            series=[EventsNode(event="$pageview")],
            dateRange=InsightDateRange(date_from="-7d"),
            breakdownFilter=BreakdownFilter(
                breakdowns=[
                    Breakdown(
                        value="$browser",
                    )
                ],
                breakdown_limit=1,
            ),
        )

        result = self._get_actors(trends_query=source_query, day="2023-04-29", breakdown=["Chrome"])

        self.assertEqual(len(result), 1)
        self.assertEqual(get_distinct_id(result[0]), "person1")
        self.assertEqual(get_event_count(result[0]), 2)

        result = self._get_actors(
            trends_query=source_query, day="2023-04-29", breakdown=["$$_posthog_breakdown_other_$$"]
        )

        self.assertEqual(len(result), 1)
        self.assertEqual(get_distinct_id(result[0]), "person2")
        self.assertEqual(get_event_count(result[0]), 2)

    def test_trends_multiple_breakdown_null_persons(self):
        self._create_events()
        source_query = TrendsQuery(
            series=[EventsNode(event="$pageview")],
            dateRange=InsightDateRange(date_from="-7d"),
            breakdownFilter=BreakdownFilter(
                breakdowns=[
                    Breakdown(
                        value="$browser",
                    )
                ],
                breakdown_limit=1,
            ),
        )

        result = self._get_actors(trends_query=source_query, day="2023-05-06", breakdown=["Chrome"])

        self.assertEqual(len(result), 0)

        result = self._get_actors(
            trends_query=source_query, day="2023-05-06", breakdown=["$$_posthog_breakdown_null_$$"]
        )

        self.assertEqual(len(result), 1)
        self.assertEqual(get_distinct_id(result[0]), "person1")
        self.assertEqual(get_event_count(result[0]), 1)

    def test_trends_multiple_breakdowns_hogql_persons(self):
        self._create_events()
        source_query = TrendsQuery(
            series=[EventsNode(event="$pageview")],
            dateRange=InsightDateRange(date_from="-7d"),
            breakdownFilter=BreakdownFilter(
                breakdowns=[Breakdown(value="properties.some_property", type=BreakdownType.HOGQL)],
                breakdown_limit=1,
            ),
        )

        result = self._get_actors(trends_query=source_query, day="2023-05-01", breakdown=["20"])
        self.assertEqual(len(result), 1)
        self.assertEqual(get_distinct_id(result[0]), "person1")
        self.assertEqual(get_event_count(result[0]), 1)

        result = self._get_actors(trends_query=source_query, day="2023-05-01", breakdown=["10"])

        self.assertEqual(len(result), 0)

    def test_trends_breakdown_filter_by_range(self):
        self._create_numeric_events()

        source_query = TrendsQuery(
            series=[EventsNode(event="$pageview")],
            dateRange=InsightDateRange(date_from="-7d"),
            breakdownFilter=BreakdownFilter(
                breakdown="some_property",
                breakdown_histogram_bin_count=4,
            ),
        )

        # should not include 20
        result = self._get_actors(trends_query=source_query, day="2023-05-01", breakdown="[0,20]")
        self.assertEqual(len(result), 1)
        self.assertEqual(get_distinct_id(result[0]), "person1")
        self.assertEqual(get_event_count(result[0]), 1)

        # should include all
        result = self._get_actors(trends_query=source_query, day="2023-05-01", breakdown='["",""]')
        self.assertEqual(len(result), 3)

        # should include null
        result = self._get_actors(trends_query=source_query, day="2023-05-01", breakdown=BREAKDOWN_NULL_STRING_LABEL)
        self.assertEqual(len(result), 1)
        self.assertEqual(get_distinct_id(result[0]), "person3")
        self.assertEqual(get_event_count(result[0]), 1)

        # handles invalid values
        with pytest.raises(ValueError, match=".*valid float or int values.*"):
            result = self._get_actors(trends_query=source_query, day="2023-05-01", breakdown='["str","str"]')
            result = self._get_actors(trends_query=source_query, day="2023-05-01", breakdown='["str",10]')
            result = self._get_actors(trends_query=source_query, day="2023-05-01", breakdown="[10,false]")
            result = self._get_actors(trends_query=source_query, day="2023-05-01", breakdown="[{},{}]")

    def test_trends_multiple_breakdowns_filter_by_range(self):
        self._create_numeric_events()

        source_query = TrendsQuery(
            series=[EventsNode(event="$pageview")],
            dateRange=InsightDateRange(date_from="-7d"),
            breakdownFilter=BreakdownFilter(breakdowns=[Breakdown(value="some_property", histogram_bin_count=4)]),
        )

        # should not include 20
        result = self._get_actors(trends_query=source_query, day="2023-05-01", breakdown=["[0,20]"])
        self.assertEqual(len(result), 1)
        self.assertEqual(get_distinct_id(result[0]), "person1")
        self.assertEqual(get_event_count(result[0]), 1)

        # should include all
        result = self._get_actors(trends_query=source_query, day="2023-05-01", breakdown=['["",""]'])
        self.assertEqual(len(result), 3)

        # should include null
        result = self._get_actors(trends_query=source_query, day="2023-05-01", breakdown=[BREAKDOWN_NULL_STRING_LABEL])
        self.assertEqual(len(result), 1)
        self.assertEqual(get_distinct_id(result[0]), "person3")
        self.assertEqual(get_event_count(result[0]), 1)

        # handles invalid values
        with pytest.raises(ValueError, match=".*valid float or int values.*"):
            result = self._get_actors(trends_query=source_query, day="2023-05-01", breakdown=['["str","str"]'])
            result = self._get_actors(trends_query=source_query, day="2023-05-01", breakdown=['["str",10]'])
            result = self._get_actors(trends_query=source_query, day="2023-05-01", breakdown=["[10,false]"])
            result = self._get_actors(trends_query=source_query, day="2023-05-01", breakdown=["[{},{}]"])
