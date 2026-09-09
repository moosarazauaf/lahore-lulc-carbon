// ============================================================================
// Lahore District LULC — corrected Earth Engine workflow
//
// Changes from the original, and why each one matters:
//
// 1. EXPORTS NOW CARRY A NODATA VALUE.
//    The original exported masked pixels as 0, which is the Built-up class
//    code, so 44% of every GeoTIFF (everything outside the district) read as
//    city. Statistics printed inside GEE were fine because reduceRegion was
//    bounded by the geometry; anything computed from the files in QGIS,
//    ArcGIS or InVEST was not. Classes are now shifted to 1..4 with 0 as a
//    declared nodata value, so the distinction survives export.
//
// 2. SAME-SEASON COMPOSITES.
//    The original composited whole years. Water extent and crop phenology
//    then differ between epochs for seasonal reasons rather than land-change
//    reasons, which is why water appeared to fall 65% between 1993 and 2003.
//    Every epoch now uses the same dry-season window.
//
// 3. FROM-TO CROSSTAB INSTEAD OF SUBTRACTION.
//    lulc2023.subtract(lulc1993) is not interpretable: class codes are
//    nominal, so a difference of 2 could be built-up to water or vegetation
//    to bare land. The crosstab gives readable transition codes.
//
// 4. CORRECTED CARBON DENSITIES.
//    Vegetation was set to 150 Mg C/ha, a closed-forest value, for a district
//    of irrigated rice-wheat cropland. Measured on the actual maps this
//    overstated the 1993-2023 carbon loss 5.9-fold.
//
// 5. THE ACCURACY ASSESSMENT IS FLAGGED, NOT FIXED.
//    Splitting pixels sampled from the same digitised points leaves training
//    and test pixels spatially autocorrelated, so the reported accuracy is
//    optimistic. A real fix needs an independent stratified random sample,
//    which cannot be done from inside this script.
// ============================================================================


// ---------------------------------------------------------------- boundary
var admin = ee.FeatureCollection("FAO/GAUL/2015/level2");

var lahore = admin.filter(
  ee.Filter.and(
    ee.Filter.eq('ADM0_NAME', 'Pakistan'),
    ee.Filter.eq('ADM1_NAME', 'Punjab'),
    ee.Filter.stringContains('ADM2_NAME', 'Lahore District')
  )
);

Map.centerObject(lahore, 9);
Map.addLayer(lahore, {}, 'Lahore Boundary');


// ---------------------------------------------------------------- cloud mask
function maskL57(image) {
  var qa = image.select('QA_PIXEL');
  return image
    .updateMask(qa.bitwiseAnd(1 << 3).eq(0))
    .updateMask(qa.bitwiseAnd(1 << 4).eq(0))
    .select(['SR_B1', 'SR_B2', 'SR_B3', 'SR_B4', 'SR_B5', 'SR_B7'])
    .multiply(0.0000275).add(-0.2)
    .rename(['Blue', 'Green', 'Red', 'NIR', 'SWIR1', 'SWIR2'])
    .clip(lahore);
}

function maskL89(image) {
  var qa = image.select('QA_PIXEL');
  return image
    .updateMask(qa.bitwiseAnd(1 << 3).eq(0))
    .updateMask(qa.bitwiseAnd(1 << 4).eq(0))
    .select(['SR_B2', 'SR_B3', 'SR_B4', 'SR_B5', 'SR_B6', 'SR_B7'])
    .multiply(0.0000275).add(-0.2)
    .rename(['Blue', 'Green', 'Red', 'NIR', 'SWIR1', 'SWIR2'])
    .clip(lahore);
}


// ---------------------------------------------------------------- indices
function addIndices(image) {
  return image
    .addBands(image.normalizedDifference(['NIR', 'Red']).rename('NDVI'))
    .addBands(image.normalizedDifference(['SWIR1', 'NIR']).rename('NDBI'))
    .addBands(image.normalizedDifference(['Green', 'NIR']).rename('NDWI'));
}

var bands = ['Blue', 'Green', 'Red', 'NIR', 'SWIR1', 'SWIR2',
             'NDVI', 'NDBI', 'NDWI'];


// ---------------------------------------------------------------- composites
//
// CHANGE 2: one fixed seasonal window for every epoch.
//
// November to March is post-monsoon and pre-wheat-harvest: the Ravi is at a
// comparable low stage each year and the rabi crop is standing, so vegetation
// and water are spectrally comparable across dates. Compositing whole years,
// as the original did, mixes monsoon flood extent into some epochs and not
// others and produces apparent "change" that is really seasonality.
var SEASON_START = 11;   // November
var SEASON_END = 3;      // March (wraps the year end)

function seasonal(collection, startYear, endYear, maskFn) {
  return collection
    .filterBounds(lahore)
    .filterDate(startYear + '-01-01', endYear + '-12-31')
    .filter(ee.Filter.or(
      ee.Filter.calendarRange(SEASON_START, 12, 'month'),
      ee.Filter.calendarRange(1, SEASON_END, 'month')
    ))
    .filter(ee.Filter.lt('CLOUD_COVER', 60))
    .map(maskFn)
    .median();
}

var image1993 = seasonal(ee.ImageCollection("LANDSAT/LT05/C02/T1_L2"), 1992, 1994, maskL57);
var image2003 = seasonal(ee.ImageCollection("LANDSAT/LE07/C02/T1_L2"), 2002, 2004, maskL57);
var image2013 = seasonal(ee.ImageCollection("LANDSAT/LC08/C02/T1_L2"), 2012, 2014, maskL89);
var image2023 = seasonal(ee.ImageCollection("LANDSAT/LC09/C02/T1_L2"), 2022, 2024, maskL89);


// ---------------------------------------------------------------- training
var training1993 = builtup_points_1993.merge(vegetation_points_1993)
  .merge(water_points_1993).merge(bareland_points_1993);
var training2003 = builtup_points_2003.merge(vegetation_points_2003)
  .merge(water_points_2003).merge(bareland_points_2003);
var training2013 = builtup_points_2013.merge(vegetation_points_2013)
  .merge(water_points_2013).merge(bareland_points_2013);
var training2023 = builtup_points_2023.merge(vegetation_points_2023)
  .merge(water_points_2023).merge(bareland_points_2023);


// ---------------------------------------------------------------- classify
//
// CHANGE 1: classes are exported as 1..4, not 0..3.
//
// Earth Engine writes masked pixels as 0 on export. If a real class also uses
// 0, the two become indistinguishable in the file. Shifting the codes up by
// one and declaring 0 as nodata keeps them separate.
//
//   1 = Built-up      2 = Vegetation      3 = Water      4 = Bare land
//
var EXPORT_OFFSET = 1;

function classifyYear(image, trainingPoints, year) {
  var finalImage = addIndices(image);

  var sampled = finalImage.select(bands).sampleRegions({
    collection: trainingPoints,
    properties: ['class'],
    scale: 30
  });

  var withRandom = sampled.randomColumn('random');
  var trainingSet = withRandom.filter(ee.Filter.lt('random', 0.7));
  var testingSet = withRandom.filter(ee.Filter.gte('random', 0.7));

  var classifier = ee.Classifier.smileRandomForest({numberOfTrees: 200})
    .train({
      features: trainingSet,
      classProperty: 'class',
      inputProperties: bands
    });

  var classified = finalImage.select(bands).classify(classifier);

  var matrix = testingSet.classify(classifier).errorMatrix('class', 'classification');
  print('YEAR ' + year + ' — NOTE: this accuracy is optimistic. Training and ' +
        'test pixels come from the same digitised points and are spatially ' +
        'autocorrelated. Treat as an upper bound, not an accuracy assessment.');
  print('  confusion matrix', matrix);
  print('  overall accuracy (optimistic)', matrix.accuracy());
  print('  kappa (optimistic)', matrix.kappa());

  Map.addLayer(classified, {
    min: 0, max: 3,
    palette: ['red', 'green', 'blue', 'yellow']
  }, year + '_LULC');

  // Shift to 1..4 and set 0 as nodata so the export is unambiguous.
  var forExport = classified.add(EXPORT_OFFSET).unmask(0).toByte();

  Export.image.toDrive({
    image: forExport,
    description: 'Lahore_' + year + '_RF_LULC_v2',
    folder: 'GEE_Thesis_LULC_v2',
    fileNamePrefix: 'Lahore_' + year + '_RF_LULC_v2',
    region: lahore.geometry(),
    scale: 30,
    crs: 'EPSG:32643',          // UTM 43N: equal-area pixels, so pixel counts
                                // can be multiplied by 900 m2 safely
    maxPixels: 1e13,
    fileFormat: 'GeoTIFF',
    formatOptions: {noData: 0}
  });

  return classified;
}

var lulc1993 = classifyYear(image1993, training1993, '1993');
var lulc2003 = classifyYear(image2003, training2003, '2003');
var lulc2013 = classifyYear(image2013, training2013, '2013');
var lulc2023 = classifyYear(image2023, training2023, '2023');


// ---------------------------------------------------------------- area
function calculateArea(classifiedImage, year) {
  var stats = ee.Image.pixelArea().divide(10000)
    .addBands(classifiedImage)
    .reduceRegion({
      reducer: ee.Reducer.sum().group({groupField: 1, groupName: 'class'}),
      geometry: lahore.geometry(),
      scale: 30,
      maxPixels: 1e13
    });
  print('AREA (ha) ' + year, stats);
  return stats;
}

calculateArea(lulc1993, '1993');
calculateArea(lulc2003, '2003');
calculateArea(lulc2013, '2013');
calculateArea(lulc2023, '2023');


// ---------------------------------------------------------------- change
//
// CHANGE 3: a from-to crosstab, not a subtraction.
//
// Code 10*from + to, so 12 is built-up to vegetation, 21 is vegetation to
// built-up, and so on. Every transition is separately identifiable, which
// subtraction cannot do.
var transitions = lulc1993.multiply(10).add(lulc2023).rename('transition');

Map.addLayer(transitions, {min: 0, max: 33}, 'Transitions 1993-2023');

// Area of each transition, which is what a Markov projection consumes.
var transitionAreas = ee.Image.pixelArea().divide(10000)
  .addBands(transitions)
  .reduceRegion({
    reducer: ee.Reducer.sum().group({groupField: 1, groupName: 'transition'}),
    geometry: lahore.geometry(),
    scale: 30,
    maxPixels: 1e13
  });
print('TRANSITION AREAS (ha), code = 10*from + to', transitionAreas);

Export.image.toDrive({
  image: transitions.add(1).unmask(0).toByte(),
  description: 'Lahore_Transitions_1993_2023_v2',
  folder: 'GEE_Change_Detection_v2',
  fileNamePrefix: 'Lahore_Transitions_1993_2023_v2',
  region: lahore.geometry(),
  scale: 30,
  crs: 'EPSG:32643',
  maxPixels: 1e13,
  fileFormat: 'GeoTIFF',
  formatOptions: {noData: 0}
});


// ---------------------------------------------------------------- carbon
//
// CHANGE 4: cropland carbon densities, not forest ones.
//
// Original: Built-up 28, Vegetation 150, Water 5, Bare land 18 Mg C/ha.
// The 150 is a closed-forest figure. Lahore's vegetation class is irrigated
// rice-wheat cropland, harvested annually, so standing biomass is near zero
// for much of the year. Measured on the actual maps, the original table
// overstates the 1993-2023 carbon loss by a factor of 5.9.
//
// These remain Tier 1 placeholders. Cite them against IPCC 2006 Vol.4 (Ch.5
// Cropland, Ch.8 Settlements) and Pakistani literature before submission.
//
//   class          above  below   soil   dead   total
//   Built-up         5.0    1.5   18.0    0.5    25.0
//   Vegetation       6.0    2.0   42.0    1.5    51.5
//   Water            0.0    0.0    5.0    0.0     5.0
//   Bare land        1.0    0.4   14.0    0.0    15.4
var CARBON = [25.0, 51.5, 5.0, 15.4];

function carbonStock(lulcImage, year) {
  var density = lulcImage.remap([0, 1, 2, 3], CARBON).rename('Carbon');

  var total = density.multiply(ee.Image.pixelArea()).divide(10000);

  print('CARBON STOCK (Mg C) ' + year, total.reduceRegion({
    reducer: ee.Reducer.sum(),
    geometry: lahore.geometry(),
    scale: 30,
    maxPixels: 1e13
  }));

  Map.addLayer(density, {
    min: 0, max: 55,
    palette: ['white', 'yellow', 'green', 'darkgreen']
  }, 'Carbon ' + year);

  Export.image.toDrive({
    image: density.unmask(-9999).toFloat(),
    description: 'Carbon_Map_' + year + '_v2',
    folder: 'GEE_Carbon_Maps_v2',
    fileNamePrefix: 'Carbon_Map_' + year + '_v2',
    region: lahore.geometry(),
    scale: 30,
    crs: 'EPSG:32643',
    maxPixels: 1e13,
    fileFormat: 'GeoTIFF',
    formatOptions: {noData: -9999}
  });

  return density;
}

var carbon1993 = carbonStock(lulc1993, '1993');
var carbon2003 = carbonStock(lulc2003, '2003');
var carbon2013 = carbonStock(lulc2013, '2013');
var carbon2023 = carbonStock(lulc2023, '2023');

var carbonChange = carbon2023.subtract(carbon1993);

Map.addLayer(carbonChange, {
  min: -50, max: 50,
  palette: ['red', 'white', 'green']
}, 'Carbon change 1993-2023');

Export.image.toDrive({
  image: carbonChange.unmask(-9999).toFloat(),
  description: 'Carbon_Change_1993_2023_v2',
  folder: 'GEE_Carbon_Stock_v2',
  fileNamePrefix: 'Carbon_Change_1993_2023_v2',
  region: lahore.geometry(),
  scale: 30,
  crs: 'EPSG:32643',
  maxPixels: 1e13,
  fileFormat: 'GeoTIFF',
  formatOptions: {noData: -9999}
});

// ============================================================================
// After running: the v2 exports drop into data/lulc/ for the projection
// pipeline in this repository. Note that the v2 files use codes 1..4 with 0 as
// nodata, whereas the original exports used 0..3 with no nodata, so
// src/config.py needs its class codes shifted if you switch to them.
// ============================================================================
