import EnvS from "@/services/tech/EnvS";
import RoutingS from "@/services/tech/RoutingS";
import { Col } from "@/ui/base/Col";
import { Grid } from "@/ui/base/Grid";
import type { HorizontalReelCase } from "@/ui/base/HorizontalReel";
import { HorizontalReel } from "@/ui/base/HorizontalReel";
import { IconRow } from "@/ui/base/IconRow";
import { LinkButton } from "@/ui/base/LinkButton";
import { Row } from "@/ui/base/Row";
import { SectionHeading } from "@/ui/base/SectionHeading";
import { Text } from "@/ui/base/Text";
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@/ui/base/card";
import { LandingNav } from "@/ui/business/LandingNav";
import {
  CircleHelp,
  Eye,
  FileCheck2,
  HardHat,
  Home,
  Languages,
  Sparkles,
  Upload,
  UserCheck,
} from "lucide-react";
import type { LandingCopy } from "./landing/types";

export type { LandingCopy };

// ============================================================================
// Private — icons are presentation, kept out of the (localized) copy data
// ============================================================================

const SIGN_IN_URL = `${EnvS.feBaseUrl()}${RoutingS.paths.signIn()}`;

const WHAT_ICONS = [Sparkles, UserCheck, Languages];
const HOW_ICONS = [Upload, Sparkles, UserCheck, FileCheck2];

// Illustrative demo cases for the hero reel — not real report output. Photos
// and marker positions are structural (same across locales); only the text
// comes from the localized copy.
function buildReelCases(copy: LandingCopy["reel"]): HorizontalReelCase[] {
  return [
    {
      id: "WR-2214",
      photo: "/landing/verdict-case-1.jpg",
      objectPosition: "center 22%",
      mark: { mx: "62%", my: "36%" },
      tagLeft: `${copy.tagCase} WR-2214`,
      tagRight: copy.tagCloseUp,
      rows: [
        { label: copy.labelDefect, value: copy.case1Defect },
        { label: copy.labelSeverity, value: copy.severityModerate, chipTone: "warning" },
        { label: copy.labelCause, value: copy.case1Cause },
      ],
    },
    {
      id: "WR-2215",
      photo: "/landing/verdict-case-2.jpg",
      objectPosition: "center 16%",
      mark: { mx: "48%", my: "50%" },
      tagLeft: `${copy.tagCase} WR-2215`,
      tagRight: copy.tagCloseUp,
      rows: [
        { label: copy.labelDefect, value: copy.case2Defect },
        { label: copy.labelSeverity, value: copy.severityLow, chipTone: "positive" },
        { label: copy.labelCause, value: copy.case2Cause },
      ],
    },
  ];
}

// ============================================================================
// Public
// ============================================================================

export function LandingPage({ copy }: { copy: LandingCopy }) {
  return (
    <Col>
      <Row py="sm" px="md" justify="center" className="bg-destructive/10">
        <Text size="sm" color="destructive" weight="medium">
          {copy.banner}
        </Text>
      </Row>
      <LandingNav nav={copy.nav} />

      {/* Hero */}
      <Col
        as="section"
        align="center"
        textAlign="center"
        gap="lg"
        px="md"
        py="xl"
        className="mx-auto max-w-2xl"
      >
        <HorizontalReel cases={buildReelCases(copy.reel)} replayLabel={copy.reel.replay} />
        <Text size="sm" color="primary" weight="semibold" tracking="wide" className="uppercase">
          {copy.hero.eyebrow}
        </Text>
        <Text as="h1" size="display" weight="bold" tracking="tight">
          {copy.hero.headline}
        </Text>
        <Text size="lg" color="muted">
          {copy.hero.subhead}
        </Text>
        <Row gap="sm" wrap justify="center">
          <LinkButton href={SIGN_IN_URL} size="lg">
            <UserCheck aria-hidden="true" data-icon="inline-start" />
            {copy.hero.ctaPrimary}
          </LinkButton>
          <LinkButton href="#how" size="lg" variant="outline">
            <Eye aria-hidden="true" data-icon="inline-start" />
            {copy.hero.ctaSecondary}
          </LinkButton>
        </Row>
        <Text size="xs" color="muted">
          {copy.hero.trustLine}
        </Text>
      </Col>

      {/* What */}
      <Col
        id="what"
        as="section"
        gap="md"
        px="md"
        py="lg"
        className="mx-auto max-w-2xl scroll-mt-16"
      >
        <SectionHeading>{copy.what.heading}</SectionHeading>
        <Text size="lg">{copy.what.intro}</Text>
        <Col gap="sm">
          {copy.what.bullets.map((bullet, index) => (
            <IconRow key={bullet} icon={WHAT_ICONS[index]} tone="primary">
              {bullet}
            </IconRow>
          ))}
        </Col>
        <Text color="muted">{copy.what.closing}</Text>
      </Col>

      {/* Why */}
      <Col
        id="why"
        as="section"
        gap="md"
        px="md"
        py="lg"
        className="mx-auto max-w-2xl scroll-mt-16"
      >
        <SectionHeading>{copy.why.heading}</SectionHeading>
        <Text size="lg">{copy.why.intro}</Text>
        <Text color="muted">{copy.why.leadIn}</Text>
        <Col gap="sm">
          {copy.why.questions.map((question) => (
            <IconRow key={question} icon={CircleHelp} tone="accent">
              {question}
            </IconRow>
          ))}
        </Col>
        <Text color="muted">{copy.why.middle}</Text>
        <Card tone="accent">
          <CardContent>
            <Text size="lg" weight="semibold" color="accent">
              {copy.why.callout}
            </Text>
          </CardContent>
        </Card>
        <Card tone="accent">
          <CardContent>
            <IconRow icon={Home} tone="accent">
              {copy.why.renterNote}
            </IconRow>
          </CardContent>
        </Card>
      </Col>

      {/* How */}
      <Col
        id="how"
        as="section"
        gap="md"
        px="md"
        py="lg"
        className="mx-auto max-w-4xl scroll-mt-16"
      >
        <SectionHeading>{copy.how.heading}</SectionHeading>
        <Grid cols="4">
          {copy.how.steps.map((step, index) => {
            const Icon = HOW_ICONS[index];
            return (
              <Card key={step.title}>
                <CardHeader>
                  <Row gap="sm" align="center">
                    <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-primary/10">
                      <Icon aria-hidden="true" className="size-4 text-primary" />
                    </span>
                    <CardTitle>{step.title}</CardTitle>
                  </Row>
                </CardHeader>
                <CardContent grow>
                  <Text color="muted">{step.desc}</Text>
                </CardContent>
              </Card>
            );
          })}
        </Grid>
        <Text color="muted" className="mx-auto max-w-2xl">
          {copy.how.closing}
        </Text>
      </Col>

      {/* Who */}
      <Col
        id="who"
        as="section"
        gap="md"
        px="md"
        py="lg"
        className="mx-auto max-w-2xl scroll-mt-16"
      >
        <Row gap="sm" align="center">
          <HardHat aria-hidden="true" className="size-6 text-accent" />
          <SectionHeading>{copy.who.heading}</SectionHeading>
        </Row>
        <Card tone="muted">
          <CardContent>
            <Text as="p" size="lg" className="italic">
              {copy.who.quote}
            </Text>
          </CardContent>
        </Card>
      </Col>

      {/* How Much */}
      <Col
        id="how-much"
        as="section"
        gap="md"
        px="md"
        py="xl"
        className="mx-auto max-w-3xl scroll-mt-16"
      >
        <SectionHeading>{copy.howMuch.heading}</SectionHeading>
        <Card width="sm" className="mx-auto">
          <CardHeader>
            <Row gap="sm" align="center">
              <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-primary/10">
                <Sparkles aria-hidden="true" className="size-4 text-primary" />
              </span>
              <CardTitle>{copy.howMuch.aiTitle}</CardTitle>
            </Row>
          </CardHeader>
          <CardContent grow>
            <Col gap="xs">
              <Text color="muted">{copy.howMuch.aiDesc}</Text>
              <Text weight="bold" color="destructive">
                {copy.howMuch.aiNote}
              </Text>
            </Col>
          </CardContent>
          <CardFooter justify="between">
            <Text size="xl" weight="bold" color="primary">
              {copy.howMuch.aiPrice}
            </Text>
            <Text color="muted">{copy.howMuch.aiDelivery}</Text>
          </CardFooter>
        </Card>
        <Text color="muted">{copy.howMuch.note}</Text>
        <Row justify="center" py="md">
          <LinkButton href={SIGN_IN_URL} size="lg">
            <UserCheck aria-hidden="true" data-icon="inline-start" />
            {copy.howMuch.ctaBottom}
          </LinkButton>
        </Row>
      </Col>
    </Col>
  );
}
