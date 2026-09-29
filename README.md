# My rewrite of Emma's code


## execution sequence
- buildBigPossiblePairs

## after buildBigPossiblePairs
- addAuthorsInventors & calculateContributorOverlap
- encodePapersPatents & calculateContentSimilarity
- calculateCitationOverlap
- calculateFieldOverlap
- calculateGovOverlap
- calculateInstitutionOverlap
- calculateSelfPlagiarism (depends on the first part of encodePapersPatents - should separate out)

## finally
- trainRandomForest
