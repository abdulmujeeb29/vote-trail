from django.db import models


class Party(models.Model):
    acronym = models.CharField(max_length=12, unique=True)
    name = models.CharField(max_length=120)
    is_mock = models.BooleanField(default=False)

    class Meta:
        verbose_name_plural = "parties"
        ordering = ["acronym"]

    def __str__(self) -> str:
        return self.acronym


class Election(models.Model):
    class Kind(models.TextChoices):
        PRESIDENTIAL = "presidential", "Presidential"
        SENATE = "senate", "Senate"
        REPS = "reps", "House of Representatives"
        GOVERNORSHIP = "governorship", "Governorship"
        STATE_ASSEMBLY = "state_assembly", "State Assembly"
        AREA_COUNCIL = "area_council", "Area Council"

    class Status(models.TextChoices):
        UPCOMING = "upcoming", "Upcoming"
        ONGOING = "ongoing", "Ongoing"
        CONCLUDED = "concluded", "Concluded"

    slug = models.SlugField(unique=True)
    name = models.CharField(max_length=120)
    kind = models.CharField(max_length=20, choices=Kind.choices)
    date = models.DateField()
    polls_open = models.DateTimeField(null=True, blank=True)
    window_end = models.DateTimeField(null=True, blank=True, help_text="Latest valid capture time.")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.UPCOMING)
    parties = models.ManyToManyField(Party, through="ElectionParty")
    is_mock = models.BooleanField(default=False)

    def __str__(self) -> str:
        return self.name


class ElectionParty(models.Model):
    election = models.ForeignKey(Election, on_delete=models.CASCADE)
    party = models.ForeignKey(Party, on_delete=models.CASCADE)
    ballot_order = models.PositiveSmallIntegerField()

    class Meta:
        ordering = ["ballot_order"]
        unique_together = [("election", "party"), ("election", "ballot_order")]

    def __str__(self) -> str:
        return f"{self.election_id}:{self.party_id}#{self.ballot_order}"
